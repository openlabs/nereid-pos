# -*- coding: utf-8 -*-
"""
    __init__

    :copyright: (c) 2013 by Openlabs Technologies & Consulting (P) Limited
    :license: BSD, see LICENSE for more details.
"""
from trytond.pool import Pool

from .product import Product, Category


def register():
    Pool.register(
        Product,
        Category,
        module='nereid_pos', type_='model')
