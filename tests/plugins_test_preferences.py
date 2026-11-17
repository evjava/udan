from udan.core_tools_loading.api_annotated import annotated

DOMAIN = "test_preferences"


@annotated(meta={"tool_type": "inserter"})
def tange(count: int = 3) -> list[int]:
    return list(range(5, 5 + count))
