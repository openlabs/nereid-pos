# -*- coding: utf-8 -*-
"""
    configuration

    :copyright: (c) 2013 by Openlabs Technologies & Consulting (P) Limited
    :license: BSD, see LICENSE for more details.
"""

from trytond.model import ModelView, ModelSQL, ModelSingleton, fields
from trytond.pyson import Eval, Bool

__all__ = ['Configuration']


class Configuration(ModelSingleton, ModelSQL, ModelView):
    'POS Configuration'
    __name__ = 'pos.configuration'

    default_sequence = fields.Property(fields.Many2One(
        'ir.sequence', 'Sequence', help='Sequence for POS Orders',
        domain=[('code', '=', 'pos.sale')],
        required=True
    ))
    default_payment_term = fields.Property(fields.Many2One(
        'account.invoice.payment_term', 'Default Payment Term',
        states={
            'required': Bool(Eval('context', {}).get('company')),
        }
    ))
    guest_party = fields.Property(
        fields.Many2One('party.party', 'Guest Party', required=True)
    )
