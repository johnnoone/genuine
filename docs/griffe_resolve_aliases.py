import ast

from griffe import Extension, Module, ObjectNode, get_logger
from griffe.dataclasses import Alias, Attribute
from griffe.expressions import ExprAttribute, ExprName

logger = get_logger(__name__)


class MyExtension(Extension):
    def __init__(self, paths: list[str] | None = None) -> None:
        super().__init__()
        self.state_thingy = "initial stuff"
        self.paths = paths or ["genuine"]

    def on_module_members(self, node: ast.AST | ObjectNode, mod: Module) -> None:
        if mod.path not in self.paths:
            return

        for member, cur in mod.members.items():
            match cur:
                case Attribute(value=ExprAttribute(values=[ExprName(name="_0"), _])):
                    logger.debug(f"On {mod.path} force alias of {member}")
                    mod.members[member] = Alias(
                        name=cur.name,
                        target=f"genuine.bases.Genuine.{member}",
                        lineno=cur.lineno,
                        endlineno=cur.endlineno,
                        runtime=cur.runtime,
                        parent=cur.parent,
                        inherited=cur.inherited,
                    )
