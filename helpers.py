# -*- coding: utf-8 -*-
"""
    helpers

    :copyright: (c) 2013 by Openlabs Technologies & Consulting (P) Limited
    :license: BSD, see LICENSE for more details.
"""
from functools import wraps

from werkzeug.exceptions import Unauthorized
from trytond.pool import Pool
from nereid import request, abort


def basic_auth_required(function):
    """
    """
    @wraps(function)
    def decorated_function(*args, **kwargs):
        auth = request.authorization
        if not auth:
            abort(403)

        User = Pool().get('res.user')
        result = User.get_login(auth.username, auth.password)
        if not result:
            raise Unauthorized('Login Error')

        return function(*args, **kwargs)
    return decorated_function
