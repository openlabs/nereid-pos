# -*- coding: utf-8 -*-
"""
    sale

    :copyright: (c) 2013 by Openlabs Technologies & Consulting (P) Limited
    :license: BSD, see LICENSE for more details.
"""
from trytond.model import ModelSQL, fields
from trytond.pool import PoolMeta, Pool
from nereid import request, jsonify

__all__ = ['POSSale', 'Website']
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


class Website:
    """
    Nereid Website
    """
    __name__ = 'nereid.website'

    @classmethod
    def pos_login(cls):
        """
        Simple login based on the email and password

        Required post data see :class:LoginForm
        """
        auth = request.authorization

        User = Pool().get('res.user')
        result = User.get_login(auth.username, auth.password)
        return jsonify(
            success=bool(result),
            data=result
        )
