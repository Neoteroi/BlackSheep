class DocumentationException(Exception):
    pass


class DuplicatedContentTypeDocsException(DocumentationException):
    def __init__(self, content_type: str) -> None:
        super().__init__(
            f"A documentation element for content type {content_type} "
            "has already been specified. Ensure that response content items "
            "have unique type."
        )
        self.content_type = content_type


class UnsupportedUnionTypeException(DocumentationException):
    def __init__(self, unsupported_type) -> None:
        super().__init__(
            f"Union types are not supported for automatic generation of "
            "OpenAPI Documentation. The annotation that caused exception is: "
            f"{unsupported_type}."
        )
        self.unsupported_type = unsupported_type
