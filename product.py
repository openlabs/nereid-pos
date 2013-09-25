# -*- coding: utf-8 -*-
"""
    product


    :copyright: (c) 2013 by Openlabs Technologies & Consulting (P) Limited
    :license: BSD, see LICENSE for more details.
"""
from trytond.pool import PoolMeta
from nereid import request, jsonify
from .helpers import basic_auth_required

__all__ = ['Product', 'Category']
__metaclass__ = PoolMeta


class Product:
    """
    Product
    """
    __name__ = 'product.product'

    @classmethod
    @basic_auth_required
    def pos_list(cls):
        """
        Return the list of products that can be displayed on the POS

        Optional Arguments:

            category: ID of the category
        """
        categories = request.nereid_website.get_categories()

        domain = []
        category = request.args.get('category', None, type=int)

        if category in map(int, categories):
            domain.append(('category', '=', category))
        else:
            # no category specified, return all valid products
            domain.append(('category', 'in', categories))

        # TODO: Some pagination love to stop loading servers
        return jsonify(
            success=True,
            data=[
                product._json() for product in cls.search(domain)
            ]
        )


class Category:
    """
    Product Category
    """

    __name__ = 'product.category'

    @classmethod
    @basic_auth_required
    def pos_list(cls):
        """
        Return a list of categories
        """
        categories = request.nereid_website.get_categories()
        return jsonify(
            success=True,
            data=[
                category._json() for category in categories
            ]
        )
