# -*- coding: utf-8 -*-
"""
    helpers

    :copyright: (c) 2013 by Openlabs Technologies & Consulting (P) Limited
    :license: BSD, see LICENSE for more details.
"""
from functools import wraps

from werkzeug.exceptions import Unauthorized
from trytond.pool import Pool
from trytond.transaction import Transaction
from nereid import request, abort, current_app


def authenticate():
    """Sends a 401 response that enables basic auth"""
    return current_app.response_class(
        'Could not verify your access level for that URL.\n'
        'You have to login with proper credentials', 401,
        {'WWW-Authenticate': 'Basic realm="Login Required"'}
    )


def basic_auth_required(function):
    """
    """
    @wraps(function)
    def decorated_function(*args, **kwargs):
        auth = request.authorization
        if not auth:
            return authenticate()

        User = Pool().get('res.user')
        user = User.get_login(auth.username, auth.password)
        if not user:
            raise Unauthorized('Login Error')

        with Transaction().set_user(user):
            return function(*args, **kwargs)
    return decorated_function
