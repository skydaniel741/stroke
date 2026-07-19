from functools import wraps
from flask import abort, redirect, url_for
from flask_login import current_user


def admin_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if not current_user.is_authenticated or not current_user.is_admin:
            abort(403)
        return f(*args, **kwargs)
    return wrapper


def solo_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if not current_user.is_authenticated:
            abort(403)
        # Solo is a paid tier -- plan alone isn't enough, see User.has_solo_access.
        # Send anyone without access to the friendly paywall page rather than a
        # bare 403, whether they're on the free plan or solo/solo_pro but unpaid.
        if not current_user.has_solo_access:
            return redirect(url_for('solo.locked'))
        return f(*args, **kwargs)
    return wrapper


def coach_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if not current_user.is_authenticated or (current_user.role != 'coach' and not current_user.is_admin):
            abort(403)
        return f(*args, **kwargs)
    return wrapper


def parent_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if not current_user.is_authenticated or (current_user.role != 'parent' and not current_user.is_admin):
            abort(403)
        return f(*args, **kwargs)
    return wrapper
