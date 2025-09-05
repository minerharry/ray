import ast
from ast import FunctionDef, Import, ImportFrom, Module, NodeTransformer, alias
from pathlib import Path
from typing import Callable, Union

from typeshed_client import (
    ImportedName,
    ModulePath,
    NameDict,
    get_search_context,
    parse_ast,
)


## the ray.includes.* files are not compiled directly as .pxi files, but instead are included in ray._raylet. For ease of typestubbing, these each get their own stub files,
## but at runtime the objects will exist in ray._raylet. As such, to properly import these stub files as modules, one needs to redirect their imports:
class RayletModuleAdaptor(NodeTransformer):
    def visit_ImportFrom(self, node: ImportFrom) -> ImportFrom:
        if node.module and node.module.startswith("ray.includes."):
            return ImportFrom(
                "ray._raylet",
                node.names,
                node.level,
                lineno=node.lineno,
                col_offset=node.col_offset,
            )
        return node

    def visit_Import(self, node: Import) -> Import:
        newnames = []
        modified = False
        for name in node.names:
            if name.name.__contains__("ray.includes"):
                newnames.append(alias("ray._raylet", name.asname))
                modified = True
            else:
                newnames.append(name)

        if modified:
            return Import(newnames, lineno=node.lineno, col_offset=node.col_offset)
        return node


def adapt_raylet_imports(tree: Module):
    RayletModuleAdaptor().visit(tree)


def get_module_contents(tree: Module, modulename: str):
    """Get all names defined in a stubfile by its ast. Ignores imports. Will include some TypeVar names, so those need to be filtered during validation.
    Returns a dict of name:typeshed_client.NameDict items."""
    names = parse_ast(tree, get_search_context(), ModulePath(tuple()))
    contents = {}
    for name, namedict in names.items():
        if isinstance(namedict.ast, ImportedName):
            continue
        contents[name] = namedict
    return contents


raylet_stubs = [
    "python/ray/_raylet.pyi",
    "python/ray/includes/buffer.pyi",
    "python/ray/includes/common.pyi",
    "python/ray/includes/function_descriptor.pyi",
    "python/ray/includes/gcs_client.pyi",
    "python/ray/includes/global_state_accessor.pyi",
    "python/ray/includes/libcoreworker.pyi",
    "python/ray/includes/metric.pyi",
    "python/ray/includes/network_util.pyi",
    "python/ray/includes/object_ref.pyi",
    "python/ray/includes/ray_config.pyi",
    "python/ray/includes/serialization.pyi",
    "python/ray/includes/setproctitle.pyi",
    "python/ray/includes/unique_ids.pyi",
]


def parse_file(path: Union[str, Path]) -> Module:
    with open(path) as f:
        tree = ast.parse(f.read())
    return tree


# def test_raylet_stubs()


def get_defined_names(names: NameDict) -> NameDict:
    # consider: there's also the option to only typecheck exported items, though I think it should be more thorough than that
    return {n: v for n, v in names.items() if not isinstance(v.ast, ImportedName)}


#### RUNTIME VALIDATION METHODS ####
def compare_functions():
    pass


#### AST VALIDATION METHODS ####

# validates the runtime function object with the stub's ast object
def validate_functiondef(
    stub: FunctionDef, func: Callable
):  # TODO: Decorator support for changing arguments???
    ## Validate function name
    if func.__name__:
        assert stub.name == func.__name__
    # cyfunction-specific attribute. Not sure if it's always the same as __name__ but I don't think it can hurt to check
    if func.func_name:
        assert stub.name == func.func_name


#     ### Validate function arguments
