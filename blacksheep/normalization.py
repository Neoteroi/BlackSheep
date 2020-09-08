def copy_special_attributes(source_method, wrapper) -> None:
    for name in {
        "auth",
        "auth_policy",
        "auth_schemes",
        "allow_anonymous",
        "controller_type",
        "route_handler",
    }:
        if hasattr(source_method, name):
            setattr(wrapper, name, getattr(source_method, name))
