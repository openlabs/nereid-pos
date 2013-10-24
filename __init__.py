# -*- coding: utf-8 -*-
"""
    __init__

    :copyright: (c) 2013 by Openlabs Technologies & Consulting (P) Limited
    :license: BSD, see LICENSE for more details.
"""
from trytond.pool import Pool

from .product import Product, Category
from .sale import POSSale, Website, Sale, Party, PaymentLine, PaymentMode
from .payment import PaymentModeStripe
from .receipt import SaleReceipt
from .configuration import Configuration


def register():
    Pool.register(
        Product,
        Category,
        Configuration,
        POSSale,
        PaymentMode,
        PaymentLine,
        PaymentModeStripe,
        Sale,
        Party,
        Website,
        module='nereid_pos',
        type_='model'
    )
    Pool.register(
        SaleReceipt,
        module='nereid_pos',
        type_='report'
    )
