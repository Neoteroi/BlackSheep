def extend(obj, cls):
    """
    Applies a mixin to an instance of a class.

    This method is used in those scenarios where opting-in for a feature incurs a
    performance fee, so that said fee is paid only when features are used.
    """
    base_cls = obj.__class__
    base_cls_name = obj.__class__.__name__ + "_" + cls.__name__
    obj.__class__ = type(base_cls_name, (cls, base_cls), {})
