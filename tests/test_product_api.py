# -*- coding: utf-8 -*-
"""
    test_product_api

    :copyright: (c) 2013 by Openlabs Technologies & Consulting (P) Limited
    :license: BSD, see LICENSE for more details.
"""
import base64
import unittest
from decimal import Decimal

import datetime
from dateutil.relativedelta import relativedelta
import simplejson as json
import trytond.tests.test_tryton
from trytond.tests.test_tryton import POOL, USER, DB_NAME, CONTEXT
from nereid.testing import NereidTestCase
from trytond.transaction import Transaction
from trytond.tools import get_smtp_server
from trytond.config import CONFIG
from mock import patch
import stripe

CONFIG['smtp_from'] = 'from@xyz.com'


class TestProduct(NereidTestCase):
    """
    Test Product
    """

    def _create_product_category(self, name, vlist):
        """
        Creates a product category

        Name is mandatory while other value may be provided as keyword
        arguments

        :param name: Name of the product category
        :param vlist: List of dictionaries of values to create
        """
        Category = POOL.get('product.category')

        for values in vlist:
            values['name'] = name
        return Category.create(vlist)

    def _create_product_template(self, name, vlist, uri, uom=u'Unit'):
        """
        Create a product template with products and return its ID

        :param name: Name of the product
        :param vlist: List of dictionaries of values to create
        :param uri: uri of product template
        :param uom: Note it is the name of UOM (not symbol or code)
        """
        ProductTemplate = POOL.get('product.template')
        Uom = POOL.get('product.uom')

        for values in vlist:
            values['name'] = name
            values['default_uom'], = Uom.search([('name', '=', uom)], limit=1)
            values['sale_uom'], = Uom.search([('name', '=', uom)], limit=1)
            values['products'] = [
                ('create', [{
                    'uri': uri,
                    'displayed_on_eshop': True
                }])
            ]
        return ProductTemplate.create(vlist)

    def _create_fiscal_year(self, date=None, company=None):
        """
        Creates a fiscal year and requried sequences
        """
        FiscalYear = POOL.get('account.fiscalyear')
        Sequence = POOL.get('ir.sequence')
        SequenceStrict = POOL.get('ir.sequence.strict')
        Company = POOL.get('company.company')

        if date is None:
            date = datetime.date.today()

        if company is None:
            company, = Company.search([], limit=1)

        invoice_sequence, = SequenceStrict.create([{
            'name': '%s' % date.year,
            'code': 'account.invoice',
            'company': company,
        }])
        fiscal_year, = FiscalYear.create([{
            'name': '%s' % date.year,
            'start_date': date + relativedelta(month=1, day=1),
            'end_date': date + relativedelta(month=12, day=31),
            'company': company,
            'post_move_sequence': Sequence.create([{
                'name': '%s' % date.year,
                'code': 'account.move',
                'company': company,
            }])[0],
            'out_invoice_sequence': invoice_sequence,
            'in_invoice_sequence': invoice_sequence,
            'out_credit_note_sequence': invoice_sequence,
            'in_credit_note_sequence': invoice_sequence,
        }])
        FiscalYear.create_period([fiscal_year])
        return fiscal_year

    def _create_coa_minimal(self, company):
        """Create a minimal chart of accounts
        """
        AccountTemplate = POOL.get('account.account.template')
        Account = POOL.get('account.account')

        account_create_chart = POOL.get(
            'account.create_chart', type="wizard"
        )

        account_template, = AccountTemplate.search(
            [('parent', '=', None)]
        )

        session_id, _, _ = account_create_chart.create()
        create_chart = account_create_chart(session_id)
        create_chart.account.account_template = account_template
        create_chart.account.company = company
        create_chart.transition_create_account()

        receivable, = Account.search([
            ('kind', '=', 'receivable'),
            ('company', '=', company),
        ])
        payable, = Account.search([
            ('kind', '=', 'payable'),
            ('company', '=', company),
        ])
        create_chart.properties.company = company
        create_chart.properties.account_receivable = receivable
        create_chart.properties.account_payable = payable
        create_chart.transition_create_properties()

    def _get_account_by_kind(self, kind, company=None, silent=True):
        """Returns an account with given spec

        :param kind: receivable/payable/expense/revenue
        :param silent: dont raise error if account is not found
        """
        Account = POOL.get('account.account')
        Company = POOL.get('company.company')

        if company is None:
            company, = Company.search([], limit=1)

        accounts = Account.search([
            ('kind', '=', kind),
            ('company', '=', company)
        ], limit=1)
        if not accounts and not silent:
            raise Exception("Account not found")
        return accounts[0] if accounts else False

    def _create_payment_term(self):
        """Create a simple payment term with all advance
        """
        PaymentTerm = POOL.get('account.invoice.payment_term')

        return PaymentTerm.create([{
            'name': 'Direct',
            'lines': [('create', [{'type': 'remainder'}])]
        }])

    def setup_defaults(self):
        User = POOL.get('res.user')

        usd, = self.Currency.create([{
            'name': 'US Dollar',
            'code': 'USD',
            'symbol': '$',
        }])

        with Transaction().set_context(company=None):
            party1, = self.Party.create([{
                'name': 'Openlabs',
            }])
            company, = self.Company.create([{
                'party': party1.id,
                'currency': usd.id
            }])
            party2, = self.Party.create([{
                'name': 'Guest User',
            }])
            guest_user, = self.NereidUser.create([{
                'party': party2.id,
                'display_name': 'Guest User',
                'email': 'guest@openlabs.co.in',
                'password': 'password',
                'company': company.id,
            }])
            party3, = self.Party.create([{
                'name': 'Registered User',
            }])
            self.registered_user, = self.NereidUser.create([{
                'party': party3.id,
                'display_name': 'Registered User',
                'email': 'email@example.com',
                'password': 'password',
                'company': company.id,
            }])

        self.category, = self.Category.create([{
            'name': 'CategoryA',
            'uri': 'category-1'
        }])

        User.write(
            [User(USER)], {
                'main_company': company.id,
                'company': company.id
            }
        )

        CONTEXT.update(User.get_preferences(context_only=True))
        # Create fiscal year
        self._create_fiscal_year(company=company.id)

        # Create chart of accounts
        self._create_coa_minimal(company=company.id)

        # Create website
        url_map, = self.UrlMap.search([('name', '=', 'POS')], limit=1)
        en_us, = self.Language.search([('code', '=', 'en_US')])
        self.NereidWebsite.create([{
            'name': 'localhost',
            'url_map': url_map.id,
            'company': company.id,
            'application_user': USER,
            'default_language': en_us.id,
            'guest_user': guest_user,
            'categories': [('set', [self.category.id])],
            'currencies': [('set', [usd.id])],
        }])

    def setUp(self):
        """
        Set up data used in the tests.
        this method is called before each test execution.
        """
        trytond.tests.test_tryton.install_module('nereid_pos')

        self.Currency = POOL.get('currency.currency')
        self.Site = POOL.get('nereid.website')
        self.Product = POOL.get('product.product')
        self.Company = POOL.get('company.company')
        self.NereidUser = POOL.get('nereid.user')
        self.UrlMap = POOL.get('nereid.url_map')
        self.Language = POOL.get('ir.lang')
        self.NereidWebsite = POOL.get('nereid.website')
        self.Party = POOL.get('party.party')
        self.Category = POOL.get('product.category')
        self.Template = POOL.get('product.template')
        self.Uom = POOL.get('product.uom')
        self.AccountTemplate = POOL.get('account.account.template')
        self.PosConfiguration = POOL.get('pos.configuration')
        self.Sequence = POOL.get('ir.sequence')
        self.templates = {}

        self.smtplib_patcher = patch('smtplib.SMTP', autospec=True)
        self.PatchedSMTP = self.smtplib_patcher.start()
        self.mocked_smtp_instance = self.PatchedSMTP.return_value

    def tearDown(self):
        # Unpatched SMTP Lib
        self.smtplib_patcher.stop()

    def _get_auth_header(self, username='admin', password='admin'):
        return {
            'Authorization': 'Basic ' + base64.b64encode(
                username + ":" + password
            )
        }

    def _create_new_sale(self):
        PaymentTerm = POOL.get('account.invoice.payment_term')
        PosSale = POOL.get('pos.sale')

        uom, = self.Uom.search([], limit=1)
        app = self.get_app()

        self.payment_term, = PaymentTerm.create([{
            'name': 'Direct',
            'lines': [('create', [{'type': 'remainder'}])]
        }])

        # set context in company to None
        guest_party, = self.Party.create([{
            'name': 'guest',
        }])

        sequence, = self.Sequence.search([('code', '=', 'pos.sale')])

        self.PosConfiguration.write(
            [self.PosConfiguration(1)], {
                'default_sequence': sequence.id,
                'default_payment_term': self.payment_term.id,
                'guest_party': guest_party.id
            }
        )

        with app.test_client() as c:
            rv = c.post(
                '/en_US/pos/sales',
                headers=self._get_auth_header()
            )
            self.assertEqual(rv.status_code, 200)

            response = json.loads(rv.data)
            return PosSale(response['data']['id'])

    def _get_template_source(self, name):
        """
        Return templates
        """
        return self.templates.get(name)

    def test_0005_mock_setup(self):
        assert get_smtp_server() is self.PatchedSMTP.return_value

    def test_0010_product_pos_list(self):
        """
        Get list of products from the POS
        """
        with Transaction().start(DB_NAME, USER, context=CONTEXT):
            print CONFIG
            self.setup_defaults()
            uom, = self.Uom.search([], limit=1)
            values1 = {
                'name': 'Product-1',
                'category': self.category.id,
                'type': 'goods',
                'salable': True,
                'sale_uom': uom.id,
                'list_price': Decimal('10'),
                'cost_price': Decimal('5'),
                'default_uom': uom.id,
                'account_expense': self._get_account_by_kind('expense').id,
                'account_revenue': self._get_account_by_kind('revenue').id,
                'products': [
                    ('create', [{
                        'uri': 'product-1',
                        'displayed_on_eshop': True
                    }])
                ]

            }
            values2 = {
                'name': 'Product-2',
                'category': self.category.id,
                'type': 'goods',
                'salable': True,
                'sale_uom': uom.id,
                'list_price': Decimal('10'),
                'cost_price': Decimal('5'),
                'default_uom': uom.id,
                'account_expense': self._get_account_by_kind('expense').id,
                'account_revenue': self._get_account_by_kind('revenue').id,
                'products': [
                    ('create', [{
                        'uri': 'product-2',
                        'displayed_on_eshop': True
                    }])
                ]
            }
            template1, template2 = self.Template.create([values1, values2])
            app = self.get_app()

            with app.test_client() as c:

                # Fail with 401 without authentication
                rv = c.get('/en_US/pos/products')
                self.assertEqual(rv.status_code, 401)

                # Fail with 401 with wrong authentication
                rv = c.get(
                    '/en_US/pos/products',
                    headers=self._get_auth_header('wrong')
                )
                self.assertEqual(rv.status_code, 401)

                # Render all products
                rv = c.get(
                    '/en_US/pos/products',
                    headers=self._get_auth_header()
                )
                self.assertEqual(rv.status_code, 200)
                response = json.loads(rv.data)
                self.assertEqual(len(response['data']), 2)

    def test_0020_category_pos_list(self):
        """
        Get list of categories from the POS
        """
        with Transaction().start(DB_NAME, USER, context=CONTEXT):
            self.setup_defaults()
            app = self.get_app()

            with app.test_client() as c:

                # Render all categories
                rv = c.get(
                    '/en_US/pos/categories',
                    headers=self._get_auth_header()
                )
                self.assertEqual(rv.status_code, 200)
                response = json.loads(rv.data)
                self.assertEqual(len(response['data']), 1)

    def test_0030_create_pos_sale_with_default_party(self):
        """
        Create a new POS Sale with a default party
        """
        with Transaction().start(DB_NAME, USER, context=CONTEXT):
            PaymentTerm = POOL.get('account.invoice.payment_term')

            self.setup_defaults()
            uom, = self.Uom.search([], limit=1)
            app = self.get_app()

            self.payment_term, = PaymentTerm.create([{
                'name': 'Direct',
                'lines': [('create', [{'type': 'remainder'}])]
            }])

            # set context in company to None

            guest_party, = self.Party.create([{
                'name': 'guest',
            }])

            sequence, = self.Sequence.search([('code', '=', 'pos.sale')])

            self.PosConfiguration.write(
                [self.PosConfiguration(1)], {
                    'default_sequence': sequence.id,
                    'default_payment_term': self.payment_term.id,
                    'guest_party': guest_party.id
                }
            )

            with app.test_client() as c:
                rv = c.post(
                    '/en_US/pos/sales',
                    headers=self._get_auth_header()
                )
                self.assertEqual(rv.status_code, 200)

                response = json.loads(rv.data)
                self.assertEqual(
                    response['data']['sale']['id']['party']['name'],
                    'guest'
                )

    def test_0040_add_line_to_pos_sale(self):
        """
        Add product to the current sale
        """
        with Transaction().start(DB_NAME, USER, context=CONTEXT):
            self.setup_defaults()
            uom, = self.Uom.search([], limit=1)
            app = self.get_app()

            values1 = {
                'name': 'Product-2',
                'category': self.category.id,
                'salable': True,
                'sale_uom': uom.id,
                'type': 'goods',
                'list_price': Decimal('10'),
                'cost_price': Decimal('5'),
                'account_expense': self._get_account_by_kind('expense').id,
                'account_revenue': self._get_account_by_kind('revenue').id,
                'default_uom': uom.id,
                'products': [
                    ('create', [{
                        'uri': 'product-2',
                        'displayed_on_eshop': True
                    }])
                ]
            }

            template1, = self.Template.create([values1])
            pos_sale = self._create_new_sale()

            with app.test_client() as c:
                url = '/en_US/pos/sales/{0}/add_line'.format(pos_sale.id)
                rv = c.post(
                    url,
                    data={
                        'product': template1.products[0].id,
                        'quantity': 1
                    },
                    headers=self._get_auth_header()
                )
                response = json.loads(rv.data)
                self.assertEqual(
                    response['sale']['id']['total_amount'],
                    Decimal('10')
                )

    def test_0050_delete_sale_line(self):
        """
        Delete product from sale
        """
        with Transaction().start(DB_NAME, USER, context=CONTEXT):
            self.setup_defaults()
            uom, = self.Uom.search([], limit=1)
            app = self.get_app()

            values1 = {
                'name': 'Product-2',
                'category': self.category.id,
                'type': 'goods',
                'salable': True,
                'sale_uom': uom.id,
                'account_expense': self._get_account_by_kind('expense').id,
                'account_revenue': self._get_account_by_kind('revenue').id,
                'list_price': Decimal('10'),
                'cost_price': Decimal('5'),
                'default_uom': uom.id,
                'products': [
                    ('create', [{
                        'uri': 'product-2',
                        'displayed_on_eshop': True
                    }])
                ]
            }
            template1, = self.Template.create([values1])
            pos_sale = self._create_new_sale()

            with app.test_client() as c:
                url = '/en_US/pos/sales/{0}/add_line'.format(pos_sale.id)
                rv = c.post(
                    url,
                    data={
                        'product': template1.products[0].id,
                        'quantity': 1
                    },
                    headers=self._get_auth_header()
                )
                response = json.loads(rv.data)
                self.assertEqual(
                    response['sale']['id']['total_amount'],
                    Decimal('10')
                )
                sale_line_id = response['line_id']
                url = '/en_US/pos/sales/{0}/delete_line/{1}'.format(
                    pos_sale.id, sale_line_id)
                rv = c.delete(
                    url,
                    headers=self._get_auth_header()
                )
                response = json.loads(rv.data)
                self.assertEqual(
                    response['sale']['id']['total_amount'],
                    Decimal('0')
                )

    def test_0060_add_party_to_sale_with_party_id(self):
        """
        Adds a party to sale using exisitng id
        """
        with Transaction().start(DB_NAME, USER, context=CONTEXT):
            Party = POOL.get('party.party')

            self.setup_defaults()
            app = self.get_app()

            new_party, = Party.create([{
                'name': 'goodparty'
            }])

            pos_sale = self._create_new_sale()
            with app.test_client() as c:
                url = '/en_US/pos/sales/{0}/add_party'.format(pos_sale.id)
                c.post(
                    url,
                    data={
                        'party_id': new_party.id
                    },
                    headers=self._get_auth_header()
                )
                self.assertEqual(pos_sale.sale.party, new_party)

    def test_0070_add_party_to_sale_with_party_name(self):
        """
        Adds a party to sale by supplying name, phone and email
        """
        with Transaction().start(DB_NAME, USER, context=CONTEXT):
            self.setup_defaults()
            app = self.get_app()

            pos_sale = self._create_new_sale()
            with app.test_client() as c:
                url = '/en_US/pos/sales/{0}/add_party'.format(pos_sale.id)
                c.post(
                    url,
                    data={
                        'name': 'abc',
                        'phone': '123',
                        'email': 'abc@def.com'
                    },
                    headers=self._get_auth_header()
                )

                self.assertEqual(pos_sale.sale.party.name, 'abc')

                for contact in pos_sale.sale.party.contact_mechanisms:
                    if contact.type == "email":
                        email = contact.value
                    else:
                        phone = contact.value

                self.assertEqual(phone, '123')
                self.assertEqual(email, 'abc@def.com')

    def test_0080_delete_party_from_sale(self):
        """
        Deletes a party from an existing sale
        """
        with Transaction().start(DB_NAME, USER, context=CONTEXT):
            self.setup_defaults()
            app = self.get_app()

            new_party, = self.Party.create([{
                'name': 'newparty',
            }])

            pos_sale = self._create_new_sale()

            with app.test_client() as c:
                url = '/en_US/pos/sales/{0}/add_party'.format(pos_sale.id)
                c.post(
                    url,
                    data={
                        'party_id': new_party.id
                    },
                    headers=self._get_auth_header()
                )
                self.assertEqual(pos_sale.sale.party, new_party)

                url = '/en_US/pos/sales/{0}/delete_party'.format(pos_sale.id)
                c.delete(
                    url,
                    headers=self._get_auth_header()
                )
                # since after deletion of party, the party is set as
                # the guest party
                self.assertNotEqual(pos_sale.sale.party, new_party)

    def test_0090_pay(self):
        """
        Adds a payment line to the current sale
        """
        PaymentMode = POOL.get('pos.sale.payment_mode')
        Journal = POOL.get('account.journal')

        with Transaction().start(DB_NAME, USER, context=CONTEXT):
            self.setup_defaults()
            app = self.get_app()

            cash_journal, = Journal.search([
                ('type', '=', 'cash'),
            ], limit=1)

            payment_mode, = PaymentMode.create([{
                'name': 'Cash',
                'processor': 'cash',
                'journal': cash_journal.id,
            }])

            pos_sale = self._create_new_sale()
            with app.test_client() as c:
                url = '/en_US/pos/sales/{0}/make_payment'.format(pos_sale.id)
                rv = c.post(
                    url,
                    data={
                        'mode': 'Cash',
                        'amount': '10'
                    },
                    headers=self._get_auth_header()
                )
                response = json.loads(rv.data)
                self.assertEqual(response['data'][0]['state'], 'success')
                self.assertEqual(
                    response['data'][0]['reference'],
                    'paid by cash'
                )
                self.assertEqual(response['data'][0]['amount'], Decimal('10'))

    def test_0100_pay_by_card(self):
        """
        Adds a payment line with the card
        """
        PaymentMode = POOL.get('pos.sale.payment_mode')
        Journal = POOL.get('account.journal')

        with Transaction().start(DB_NAME, USER, context=CONTEXT):
            self.setup_defaults()
            app = self.get_app()

            cash_journal, = Journal.search([
                ('type', '=', 'cash'),
            ], limit=1)

            payment_mode, = PaymentMode.create([{
                'name': 'Stripe',
                'processor': 'stripe',
                'stripe_api_key': 'sk_test_MOOXLfuPHtxanjZitIfoWNZI',
                'journal': cash_journal.id,
            }])

            stripe.api_key = 'sk_test_MOOXLfuPHtxanjZitIfoWNZI'
            stripe_response = stripe.Token.create(
                card={
                    'number': '4242424242424242',
                    'exp_month': 12,
                    'exp_year': 2013,
                    'cvc': 123
                }
            )
            stripe_token = stripe_response['id']
            pos_sale = self._create_new_sale()
            with app.test_client() as c:
                url = '/en_US/pos/sales/{0}/make_payment'.format(pos_sale.id)
                rv = c.post(
                    url,
                    data={
                        'mode': 'Stripe',
                        'amount': '1000',
                        'stripe_token': stripe_token
                    },
                    headers=self._get_auth_header()
                )
                response = json.loads(rv.data)
                self.assertEqual(
                    response['data'][0]['reference'], stripe_token
                )
                self.assertEqual(
                    response['data'][0]['state'], 'success'
                )

    def test_0110_pay_by_failed_card(self):
        """
        Adds a payment line with state failed because card info is wrong
        """
        PaymentMode = POOL.get('pos.sale.payment_mode')
        Journal = POOL.get('account.journal')

        with Transaction().start(DB_NAME, USER, context=CONTEXT):
            self.setup_defaults()
            app = self.get_app()

            cash_journal, = Journal.search([
                ('type', '=', 'cash'),
            ], limit=1)

            payment_mode, = PaymentMode.create([{
                'name': 'Stripe',
                'processor': 'stripe',
                'stripe_api_key': 'sk_test_MOOXLfuPHtxanjZitIfoWNZI',
                'journal': cash_journal.id,
            }])

            stripe.api_key = 'sk_test_MOOXLfuPHtxanjZitIfoWNZI'
            stripe_response = stripe.Token.create(
                card={
                    'number': '4000000000000002',
                    'exp_month': 12,
                    'exp_year': 2013,
                    'cvc': 123
                }
            )
            stripe_token = stripe_response['id']
            pos_sale = self._create_new_sale()
            with app.test_client() as c:
                url = '/en_US/pos/sales/{0}/make_payment'.format(pos_sale.id)
                rv = c.post(
                    url,
                    data={
                        'mode': 'Stripe',
                        'amount': '1000',
                        'stripe_token': stripe_token
                    },
                    headers=self._get_auth_header()
                )
                response = json.loads(rv.data)
                self.assertEqual(
                    response['data'][0]['state'], 'failed'
                )

    def test_0130_receipt_test(self):
        """
        Tests to check if the receipt is made
        """
        with Transaction().start(DB_NAME, USER, context=CONTEXT):
            self.setup_defaults()
            app = self.get_app()

            pos_sale = self._create_new_sale()
            with app.test_client() as c:
                url = '/en_US/pos/sales/{0}/make_receipt'.format(pos_sale.id)
                c.get(url, headers=self._get_auth_header())
                self.assertTrue(pos_sale.sale_receipt_cache)

    def test_0120_send_email_with_default_party(self):
        """
        Tests to chek if the default party is set, uses email id from
        form data, to send email
        """
        with Transaction().start(DB_NAME, USER, context=CONTEXT):
            self.setup_defaults()
            app = self.get_app()

            pos_sale = self._create_new_sale()
            with app.test_client() as c:
                url = '/en_US/pos/sales/{0}/send_email'.format(pos_sale.id)
                c.post(
                    url,
                    data={
                        'email_id': 'udit.wal@gmail.com'
                    },
                    headers=self._get_auth_header()
                )


def suite():
    "Test suite"
    test_suite = unittest.TestSuite()
    test_suite.addTests(
        unittest.TestLoader().loadTestsFromTestCase(TestProduct)
    )
    return test_suite


if __name__ == '__main__':
    unittest.TextTestRunner(verbosity=2).run(suite())
