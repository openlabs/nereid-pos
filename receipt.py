# -*- coding: utf-8 -*-
"""
    receipt

    POS Sale Module

    :copyright: (c) 2013 by Openlabs Technologies & Consulting (P) Limited
    :license: BSD, see LICENSE for more details.
"""
from trytond.report import Report
from trytond.pool import Pool, PoolMeta
from trytond.transaction import Transaction
from pytz import timezone, utc
from babel.dates import format_date, format_time

__all__ = ['SaleReceipt']
__metaclass__ = PoolMeta


class SaleReceipt(Report):
    """
    Sale Receipt
    """
    __name__ = 'pos.sale.receipt'

    @classmethod
    def parse(cls, report, objects, data, localcontext):
        """
        Adds variables into the context required for rendering
        the report
        """
        PosSale = Pool().get('pos.sale')

        pos_sale = PosSale(data.get('id'))

        tz = timezone(Transaction().context.get('timezone') or 'UTC')
        sale_datetime = utc.localize(pos_sale.create_date)
        sale_datetime.astimezone(tz)

        localcontext.update({
            'pos_sale': pos_sale,
            'sale_date': format_date(
                sale_datetime.date(),
                locale=Transaction().language
            ),
            'sale_time': format_time(
                sale_datetime.time(),
                locale=Transaction().language
            ),
        })

        res = super(SaleReceipt, cls).parse(
            report, objects, data, localcontext
        )
        return res
