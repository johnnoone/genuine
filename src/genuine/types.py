from collections.abc import Mapping
from typing import Any, TypeAlias

Context: TypeAlias = Mapping[str, Any]
"""
Set of attributes currently being collected and transient data.
"""
