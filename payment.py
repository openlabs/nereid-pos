# -*- coding: utf-8 -*-
"""
    payment

    :copyright: (c) 2013 by Openlabs Technologies & Consulting (P) Limited
    :license: BSD, see LICENSE for more details.
"""
from trytond.pool import Pool, PoolMeta
from nereid import request
from trytond.model import fields
from trytond.pyson import Eval

try:
    import stripe
except ImportError:
    stripe = None

__metaclass__ = PoolMeta
__all__ = ['PaymentModeStripe']


class PaymentModeStripe:
    "Payment Processor for Stripe"

    __name__ = "pos.sale.payment_mode"

    stripe_api_key = fields.Char(
        'Stripe API Key', states={
            'invisible': Eval('processor') != 'stripe',
            'required': Eval('processor') == 'stripe'
        }, depends=['processor']
    )

    @classmethod
    def __setup__(cls):
        """
        Add stripe as a payment method if the API exists
        """
        super(PaymentModeStripe, cls).__setup__()
        mode_selection = ('stripe', 'Stripe')
        if stripe and mode_selection not in cls.processor.selection:
            cls.processor.selection.append(mode_selection)

    def _process_stripe(self, payment_line):
        """
        Process the payment using stripe

        :param payment_line: Active record of the payment line
        """
        PaymentLine = Pool().get('pos.sale.payment_line')
        token = request.values['stripe_token']

        # Call up the stripe server and check if the payment succeeded
        # Record any transaction reference into the payment_line
        # Write success as state to the payment line
        stripe.api_key = self.stripe_api_key

        # Multiplying amount by 100, because the amount charged by
        # sprite is in cents
        # TODO: Use the order reference generated in the description
        try:
            stripe.Charge.create(
                amount=payment_line.amount * 100,
                currency=payment_line.pos_sale.sale.currency.code,
                card=token,
                description='For Sale ID:{0}'.format(
                    payment_line.pos_sale.sale.id
                )
            )
        except stripe.CardError, e:
            PaymentLine.write([payment_line], {
                'reference': '{0} reason for failure {1}'.format(token, e),
                'state': 'failed'
            })
        else:
            return PaymentLine.write([payment_line], {
                'reference': token,
                'state': 'success'
            })
