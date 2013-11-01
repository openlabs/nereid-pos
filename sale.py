# -*- coding: utf-8 -*-
"""
    sale

    :copyright: (c) 2013 by Openlabs Technologies & Consulting (P) Limited
    :license: BSD, see LICENSE for more details.
"""
from trytond.model import ModelSQL, ModelView, fields
from trytond.pool import PoolMeta, Pool
from .helpers import basic_auth_required
from nereid import request, jsonify, render_email
from trytond.transaction import Transaction
from decimal import Decimal
from jinja2 import Template
from trytond.tools import get_smtp_server
from trytond.config import CONFIG

__all__ = ['POSSale', 'Website', 'Sale', 'Party', 'PaymentMode', 'PaymentLine']
__metaclass__ = PoolMeta


class POSSale(ModelSQL):
    """
    A Draft Sale Order is maintained through out the process of the existance
    of a pos.sale which is finally converted into a confirmed sale order once
    the process is complete.
    """
    __name__ = 'pos.sale'

    sale = fields.Many2One(
        'sale.sale', 'Sale Order', select=True, required=True
    )
    website = fields.Many2One(
        'nereid.website', 'Website', select=True
    )
    payment_lines = fields.One2Many(
        'pos.sale.payment_line', 'pos_sale', 'Payment Lines'
    )
    sale_receipt_cache = fields.Binary('Sale Receipt', readonly=True)

    def _json(self):
        """
        Return a dictionary which is JSON serializable
        """
        return {
            'id': self.id,
            'sale': {
                'id': self.sale._json(),
            }
        }

    @classmethod
    @basic_auth_required
    def create_new_sale(cls):
        """
        Creates a new sale order for this pos sale

        Form Data

            party: Id of the party (if not provided use default guest)
            invoice_address: ID of the invoice address
            shipment_address: ID of the shipment address
        """
        Sale = Pool().get('sale.sale')
        POSConfiguration = Pool().get('pos.configuration')
        Party = Pool().get('party.party')

        configuration = POSConfiguration(1)

        party = request.form.get('party', None, type=int)
        if not party:
            # neither party nor name for a party is specified
            # so lookup the configuration and the default party
            # from there
            party = configuration.guest_party
        else:
            # Make it an active record
            party = Party(party)

        sale, = Sale.create([{
            'party': party.id,
            'invoice_address': request.form.get(
                'invoice_address', party.addresses[0].id, type=int
            ),
            'shipment_address': request.form.get(
                'shipment_address', party.addresses[0].id, type=int
            ),
            'is_pos': True,
            'payment_term': configuration.default_payment_term.id
        }])

        return sale

    @classmethod
    @basic_auth_required
    def render_list(cls):
        """
        Creates a new pos sale
        """
        if request.method == 'POST':
            pos_sale, = cls.create([{
                'sale': cls.create_new_sale()
            }])
            return jsonify(
                data=pos_sale._json()
            )

        sales = cls.search([
            ('create_uid', '=', Transaction().user)
        ], limit=20)

        return jsonify(
            data=[
                sale._json() for sale in sales
            ]
        )

    @basic_auth_required
    def add_line(self):
        """
        Creates a new line of Product for the sale, or updates one if
        already exists

        Form Data:
            sale: Integer ID
            product: Integer ID
            quantity: decimal

        Reponse:
            'Subtotal': decimal
            'Taxes Total': decimal
            'Total': decimal
        """
        sale_line = self.sale._add_or_update(
            request.form.get('product', type=int),
            request.form.get('quantity', type=float)
        )
        response = self._json()
        response['line_id'] = sale_line.id
        return jsonify(response)

    @basic_auth_required
    def delete_line(self, line_id):
        """
        Deletes a line from the sale

        Form Data:
            line_id: Id of the Line

        Response:
            'OK' if delete succesful
        """
        if request.method == "DELETE":
            if self.sale._delete_line(line_id):
                return jsonify(self._json())

    @basic_auth_required
    def add_party_to_sale(self):
        """
        Adds a party to a sale if party id is given, else uses
        the name, email and phone field to create a new party
        and then sets it
        """
        Sale = Pool().get('sale.sale')
        Party = Pool().get('party.party')

        if request.method == "POST":
            if request.form.get('party_id', type=int):
                party = Party(request.form.get('party_id', type=int))
                Sale.write([self.sale], {
                    'party': party,
                    'invoice_address': party.addresses[0].id,
                    'shipment_address': party.addresses[0].id,
                })
            else:
                name = request.form.get('name', type=str)
                phone = request.form.get('phone', type=str)
                email = request.form.get('email', type=str)
                party_values = {
                    'name': name,
                    'contact_mechanisms': []
                }
                if phone:
                    party_values['contact_mechanisms'].append((
                        'create', [{
                            'type': 'phone',
                            'value': phone
                        }]
                    ))
                if email:
                    party_values['contact_mechanisms'].append((
                        'create', [{
                            'type': 'email',
                            'value': email
                        }]
                    ))

                party, = Party.create([party_values])
                Sale.write([self.sale], {
                    'party': party.id,
                    'invoice_address': party.addresses[0].id,
                    'shipment_address': party.addresses[0].id,
                })
            return jsonify()

    @basic_auth_required
    def delete_party_from_sale(self):
        """
        Deletes a party from a sale
        """
        Sale = Pool().get('sale.sale')
        POSConfiguration = Pool().get('pos.configuration')

        config = POSConfiguration(1)
        if request.method == "DELETE":
            party = config.guest_party
            Sale.write([self.sale], {
                'party': party,
                'invoice_address': party.addresses[0].id,
                'shipment_address': party.addresses[0].id
            })
            return jsonify()

    @basic_auth_required
    def pay(self):
        """
        Adds a payment line to sale, the incoming mode will
        either be 'card' or 'cash', if it's card, it calls
        the payment line with pay_by_card method which
        processes the payment, and then adds the payment
        line into the database, if the verification fails,
        then the payment line is saved with a failed boolean
        true

        Form Data:
            mode: id of the mode
            amount: amount that has been entered with the
                    payment line
            token: if the payment method is sprite
        Response:
            payment line details: details of the payment line
            code: if action succeeded or failed
        """
        PaymentLine = Pool().get('pos.sale.payment_line')
        PaymentMode = Pool().get('pos.sale.payment_mode')

        if request.method == "POST":
            payment_mode = request.form.get('mode', str)
            amount = request.form.get('amount', str)
            payment_mode, = PaymentMode.search([('name', '=', payment_mode)])
            payment_line, = PaymentLine.create([{
                'pos_sale': self.id,
                'processor': payment_mode.id,
                'amount': Decimal(amount),
                'state': 'draft'
            }])
            payment_mode.process(payment_line)
            return jsonify(
                data=[
                    line._json() for line in self.payment_lines
                ]
            )

    @basic_auth_required
    def make_receipt(self):
        """
        Makes a receipt for the current sale
        """
        SaleReceipt = Pool().get('pos.sale.receipt', type='report')
        PosSale = Pool().get('pos.sale')

        if not self.sale_receipt_cache:
            report = SaleReceipt.execute([], {'id': self.id})
            PosSale.write([self], {'sale_receipt_cache': report[1]})
        self = PosSale(self)
        return jsonify({
            'data': ''.join(list(self.sale_receipt_cache)).encode('base64')
        })

    @basic_auth_required
    def send_receipt_email(self):
        """
        Sends an email for the receipt

        Form Data:
            email_id: Email ID of Party
        Response:
            success: if send email succesful
        """
        if request.form.get('email_id'):
            email_to = request.form.get('email_id')
        else:
            contact_mechanisms = self.sale.party.contact_mechanisms
            for contact_mechanism in contact_mechanisms:
                if contact_mechanism.type == "email":
                    email_to = contact_mechanism.value

        print email_to
        message = render_email(
            from_email=CONFIG['smtp_from'],
            to=email_to,
            subject='Receipt from {0}'.format(
                Transaction().context.get('company')
            ),
            attachments={
                'receipt.pdf': self.sale_receipt_cache
            },
            text_template=Template("hello")
        )
        server = get_smtp_server()
        server.sendmail(
            CONFIG['smtp_from'], email_to,
            message.as_string()
        )
        server.quit()
        return jsonify({
            'success': 'True'
        })


class Website:
    """
    Nereid Website
    """
    __name__ = 'nereid.website'

    @classmethod
    @basic_auth_required
    def pos_login(cls):
        """
        Simple login based on the email and password

        Required post data see :class:LoginForm
        """
        return jsonify()


class Sale:
    "Sale"
    __name__ = 'sale.sale'

    is_pos = fields.Boolean('POS Order', readonly=True)
    pos_sales = fields.One2Many('pos.sale', 'sale', 'POS Sales', readonly=True)

    @staticmethod
    def default_is_pos():
        """
        By Default orders are not POS orders
        """
        return False

    def _json(self):
        """
        Return a JSON serializable dictionary of the order
        """
        return {
            'id': self.id,
            'party': self.party._json(),
            'untaxed_amount': self.untaxed_amount,
            'tax_amount': self.tax_amount,
            'total_amount': self.total_amount
        }

    def _add_or_update(self, product_id, quantity):
        """
        Add item as a line or update if a line if item exists

        :param product_id: ID of product
        :param quantity: Quantity
        """
        SaleLine = Pool().get('sale.line')

        lines = SaleLine.search([
            ('sale', '=', self.id),
            ('product', '=', product_id)
        ])

        if lines:
            order_line = lines[0]
            values = {
                'product': product_id,
                '_parent_sale.currency': self.currency.id,
                '_parent_sale.party': self.party.id,
                'unit': order_line.unit.id,
                'quantity': quantity + order_line.quantity,
                'type': 'line',
            }
            values.update(SaleLine(**values).on_change_quantity())

            new_values = {}
            for key, value in values.iteritems():
                if '.' not in key:
                    new_values[key] = value
                if key == 'taxes' and value:
                    new_values[key] = [('set', value)]
            SaleLine.write([order_line], new_values)
            return order_line
        else:
            values = {
                'product': product_id,
                '_parent_sale.currency': self.currency.id,
                '_parent_sale.party': self.party.id,
                'sale': self.id,
                'type': 'line',
                'quantity': quantity,
                'unit': None,
                'description': None
            }
            values.update(SaleLine(**values).on_change_product())
            values.update(SaleLine(**values).on_change_quantity())
            new_values = {}
            for key, value in values.iteritems():
                if '.' not in key:
                    new_values[key] = value
                if key == 'taxes' and value:
                    new_values[key] = [('set', value)]
            return SaleLine.create([new_values])[0]

    def _delete_line(self, line_id):
        """
        Delete item line from order if a line exists for the current product ID
        :param line_id: ID of line
        """
        SaleLine = Pool().get('sale.line')

        lines = SaleLine.search([
            ('sale', '=', self.id),
        ])

        if lines:
            SaleLine.delete([lines[0]])
            return True
        else:
            return False


class PaymentLine(ModelSQL, ModelView):
    "Payment Line"
    __name__ = "pos.sale.payment_line"

    pos_sale = fields.Many2One(
        'pos.sale', 'POS Sale', required=True, select=True
    )
    amount = fields.Numeric('Amount', digits=(16, 4), required=True)
    processor = fields.Many2One(
        'pos.sale.payment_mode', 'Processor', required=True
    )
    reference = fields.Char('Reference')
    notes = fields.Text('Notes')
    state = fields.Selection([
        ('draft', 'Draft'),
        ('success', 'Success'),
        ('failed', 'Failed'),
    ], 'State')

    def _json(self):
        """
        Returns a JSON Serializable Dictionary
        """
        return {
            'id': self.id,
            'amount': self.amount,
            'reference': self.reference,
            'state': self.state
        }


class PaymentMode(ModelSQL, ModelView):
    """'
    Payment Modes
    =============

    This model stores the different alternatives available to the POS User
    to pay for their orders

    Two modes available by default are of type cash and card. When the mode
    is card, additional options are made available for the user to configure
    settings of a payment gateway provider.
    """
    __name__ = "pos.sale.payment_mode"

    name = fields.Char('Name', required=True)
    journal = fields.Many2One('account.journal', 'Journal', required=True)
    processor = fields.Selection(
        [(None, ''), ('cash', 'Cash')],
        'Payment Processor'
    )

    def process(self, payment_line):
        """
        Process the card by calling the corresponding gateway

        :param payment_line: payment line active record
        """
        # find the method to be called based on the
        # card processor of this method
        method = getattr(self, '_process_{0}'.format(self.processor))
        return method(payment_line)

    def _process_cash(self, payment_line):
        """
        Cash is as easy as paying by cash

        :param payment_line: payment line active record
        """
        payment_line.state = 'success'
        payment_line.reference = 'paid by cash'
        payment_line.save()
        return True


class Party:
    "Party"
    __name__ = 'party.party'

    @classmethod
    @basic_auth_required
    def render_list(cls):
        """
        Returns the list of party that are on the server
        """
        if request.method == "GET":
            return jsonify(
                parties=[party._json() for party in cls.search([])]
            )

    def _json(self):
        """
        Returns a json serializable format for the current party
        """
        return {
            'id': self.id,
            'name': self.name,
            'phone': self.phone,
            'email': self.email,
            'invoice_address': self.addresses[0].id
        }
