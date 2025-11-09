import itertools
import operator
import types
from enum import Enum
from pathlib import Path
from typing import Any, Callable, DefaultDict, Optional, Union

# use CST instead of AST to allow stub testing directives with comments
from libcst import (
    AnnAssign,
    Annotation,
    Attribute,
    BaseAssignTargetExpression,
    BaseSmallStatement,
    BaseStatement,
    Comment,
    CSTNode,
    CSTTransformer as NodeTransformer,
    CSTVisitor as Visitor,
    EmptyLine,
    FunctionDef,
    Import,
    ImportAlias as alias,
    ImportFrom,
    ImportStar,
    MetadataWrapper,
    Module,
    Name,
    Newline,
    RemovalSentinel,
    RemoveFromParent,
    SimpleStatementLine,
    TrailingWhitespace,
    VisitorMetadataProvider,
    parse_expression,
    parse_module,
)
from libcst._flatten_sentinel import FlattenSentinel
from libcst.metadata import (
    Assignment,
    ClassScope,
    CodeRange,
    GlobalScope,
    ParentNodeProvider,
    PositionProvider,
    ScopeProvider,
)
from typeshed_client import (
    ImportedName,
    NameDict,
)

# def get_module_contents(tree: Module, modulename: str):
#     """Get all names defined in a stubfile by its ast. Ignores imports. Will include some TypeVar names, so those need to be filtered during validation.
#     Returns a dict of name:typeshed_client.NameDict items."""
#     names = parse_ast(tree, get_search_context(), ModulePath(tuple()))
#     contents = {}
#     for name, namedict in names.items():
#         if isinstance(namedict.ast, ImportedName):
#             continue
#         contents[name] = namedict
#     return contents


raylet_include_stubs = [
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
raylet_file = "python/ray/_raylet.pyi"
stubfiles = raylet_include_stubs + [raylet_file]

stub_module_dict = {
    name.replace("python/", "").replace("/", ".").replace(".pyi", ""): name
    for name in stubfiles
}


def parse_file(path: Union[str, Path]) -> Module:
    with open(path) as f:
        tree = parse_module(f.read())
    return tree


# def test_raylet_stubs()


def get_defined_names(names: NameDict) -> NameDict:
    # consider: there's also the option to only typecheck exported items, though I think it should be more thorough than that
    return {n: v for n, v in names.items() if not isinstance(v.ast, ImportedName)}


#### AST VALIDATION METHODS ####

# validates the runtime function object with the stub's ast object
def validate_functiondef(stub: FunctionDef, func: Callable):
    ## Check for dangerous decorators!
    for decorator in stub.decorator_list:
        """"""

    ## Validate function name
    if func.__name__:
        assert stub.name == func.__name__
    # cyfunction-specific attribute. Not sure if it's always the same as __name__ but I don't think it can hurt to check
    if func.func_name:
        assert stub.name == func.func_name

    ### Validate function arguments

    ### Validate docstring contents


#### RUNTIME VALIDATION METHODS ####
class StubDirective(Enum):
    REMOVE = "remove"  # delete node from syntax tree
    PRESERVE_IMPORT = "preserve-import"  # don't turn a ray import from a stubbed file into a stub import


class GetAttrName(Visitor):
    @classmethod
    def get_attribute_name(cls, attr: Union[Attribute, Name]):
        c = cls()
        attr.visit(c)
        return c.attrname

    def __init__(self):
        self.attrname = ""

    def visit_Attribute(self, node: Attribute) -> bool:
        node.value.visit(self)
        self.attrname += "."
        node.attr.visit(self)
        return False

    def visit_Name(self, node: Name) -> Optional[bool]:
        self.attrname += node.value
        return False


def getattrname(node: Union[Attribute, Name]):
    return GetAttrName.get_attribute_name(node)


## CST Visitor to extract trailing comments which start with "stub-testing: ". Stored as metadata in the statement which owns the comment. To access from child nodes,
## use ParentMetadataProvider
class StubCommentMetadataProvider(VisitorMetadataProvider[str]):
    def __init__(self):
        self.current_line: list[CSTNode] = []
        self.current_comment: Optional[str] = None

    def handle_comment(self, comment: Optional[Comment]):
        if not comment:
            return
        commentstr = comment.value
        if commentstr.lstrip("#").lstrip().startswith("stub-testing:"):  # relevant
            print("relevant comment found: ", commentstr)
            self.current_comment = commentstr.split("stub-testing:")[1].strip()

    def handle_newline(
        self,
    ):  # flush the current list of nodes on this line, applying the comment data if there is any
        if self.current_comment:
            for node in self.current_line:
                self.set_metadata(node, self.current_comment)

        self.current_line = []
        self.current_comment = None

    ## handle the nodes which actually have comments
    def visit_TrailingWhitespace_comment(self, node: TrailingWhitespace) -> None:
        self.handle_comment(node.comment)

    def leave_EmptyLine_comment(self, node: EmptyLine) -> None:
        self.handle_comment(node.comment)

    def leave_Newline(self, original_node: Newline) -> None:
        self.handle_newline()

    def on_visit(self, node: CSTNode) -> bool:
        self.current_line.append(node)
        return super().on_visit(node)

    # ## then handle the nodes which potentiall have comment-havers as children, and propagate appropriately IF they are on the same line
    # def on_leave(self, original_node: CSTNode) -> None:
    #     def comment(node:CSTNode):
    #         return self.get_metadata(StubCommentMetadataProvider,node,default=None)
    #     if   isinstance(original_node, SimpleStatementLine):
    #         if (c := comment(original_node.trailing_whitespace)):
    #             self.set_metadata(original_node,c)
    #             return
    #     elif isinstance(original_node, ParenthesizedWhitespace):
    #         if (c := comment(original_node.first_line)):
    #             self.set_metadata(original_node,c)
    #             return
    #     elif isinstance(original_node, Comma):
    #         ...

    #     elif isinstance(ws := getattr(original_node,"whitespace_after",None),ParenthesizedWhitespace): #unless caught above, assume the node is atomic and followed by a whitespace - that is, the entire op should be flagged by the comment
    #         if (c := comment(ws)):
    #             self.set_metadata(original_node,c)
    #             return

    #     if isinstance(original_node,(BaseStatement,BaseSmallStatement,SimpleStatementLine, ParenthesizedWhitespace, Comma)):
    #         for child in original_node.children:
    #             chmet = self.get_metadata(StubCommentMetadataProvider,child,default=None)
    #             if chmet:
    #                 print("child metadata found")
    #                 print(chmet,type(original_node))
    #                 self.set_metadata(original_node,chmet)
    #                 break # TODO: Multiple children for multi-line statements?


class RemoveIgnoredLines(NodeTransformer):
    METADATA_DEPENDENCIES = (StubCommentMetadataProvider,)

    def on_leave(
        self, original_node: CSTNode, updated_node: CSTNode
    ) -> Union[CSTNode, RemovalSentinel, FlattenSentinel[CSTNode]]:
        if isinstance(
            updated_node, (BaseStatement, BaseSmallStatement, SimpleStatementLine)
        ):
            met = self.get_metadata(
                StubCommentMetadataProvider, original_node, default=None
            )
            if met == StubDirective.REMOVE.value:
                print("Removing bad statement")
                return EmptyLine()
        return updated_node


def tuplify(a: alias, b: CSTNode, r: CodeRange):
    return (
        getattrname(a.name),
        a.asname.name.value if a.asname else None,
        b,
        r,
    )  # since a is an import alias, AsName will always be a single name, not a tuple


## Modifies the ast for a stub file (either _raylet.pyi or an includes/*.pyi file) which potentially imports from an includes.pyi file
## Specifically, calling .extract_imports() removes any `import ray.includes.*` or `from ray.includes.* import []` statements from the tree,
## and returns the removed imports so that they can be provided via the namespace to 'exec'.
class IncludesImportAdaptor(NodeTransformer):
    METADATA_DEPENDENCIES = (
        StubCommentMetadataProvider,
        ParentNodeProvider,
        PositionProvider,
    )

    def __init__(self):
        # namespace: [(symbol,alias|None) or (None,alias|None)] for from [namespace] import [symbol] as [alias|None] and import [namespace] as [alias|None] respectively
        self.module_imports: dict[
            str, list[tuple[Optional[str], Optional[str], CSTNode, CodeRange]]
        ] = DefaultDict(list)

    @classmethod
    def extract_imports(cls, tree: Union[Module, MetadataWrapper]):
        c = cls()
        newtree = tree.visit(c)
        return newtree, c.module_imports

    def leave_ImportFrom(
        self, original_node: ImportFrom, updated_node: ImportFrom
    ) -> Union[ImportFrom, RemovalSentinel]:
        node = updated_node
        parent = self.get_metadata(ParentNodeProvider, node, default=None)
        if parent:
            meta = self.get_metadata(StubCommentMetadataProvider, parent)
            if meta == StubDirective.PRESERVE_IMPORT.value:
                return node

        if node.module:
            modulename = getattrname(node.module)
            if modulename in stub_module_dict:
                # print("removing import",modulename)
                range: CodeRange = self.get_metadata(PositionProvider, original_node)
                if isinstance(node.names, ImportStar):
                    self.module_imports[modulename].append(("*", None, node, range))
                else:
                    self.module_imports[modulename].extend(
                        map(
                            tuplify,
                            node.names,
                            itertools.repeat(node),
                            itertools.repeat(range),
                        )
                    )
                return RemoveFromParent()
        return node

    def leave_Import(
        self, original_node: Import, updated_node: Import
    ) -> Union[Import, RemovalSentinel]:
        node = updated_node
        parent = self.get_metadata(ParentNodeProvider, node, default=None)
        if parent:
            meta = self.get_metadata(StubCommentMetadataProvider, parent)
            if meta == StubDirective.PRESERVE_IMPORT.value:
                return node

        newnames = []
        modified = False
        for name in node.names:
            modulename = getattrname(name.name)
            if modulename in stub_module_dict:
                print("removing import", getattrname(name.name))
                range: CodeRange = self.get_metadata(PositionProvider, original_node)
                self.module_imports[modulename].append(
                    (
                        None,
                        getattrname(name.asname.name) if name.asname else None,
                        node,
                        range,
                    )
                )
                modified = True
            else:
                newnames.append(name)
        if modified:
            if len(newnames) == 0:
                return RemoveFromParent()
            return Import(newnames)
        return node


class VariableAnnotation:  # special type for loading a global variable from a .pyi with no name, and so no namespace registry. This gets registered in its place
    __var_annotations: dict[int, "VariableAnnotation"] = {}

    @classmethod
    def get(cls, _id: int):
        return cls.__var_annotations[_id]

    @classmethod
    def put(cls, _id: int, ann: "VariableAnnotation"):
        cls.__var_annotations[_id] = ann

    def __init__(
        self, target: BaseAssignTargetExpression, annotation: Annotation
    ) -> None:
        pass


class EmptyAnnAssignDefaulter(NodeTransformer):
    METADATA_DEPENDENCIES = (ScopeProvider, ParentNodeProvider)

    def leave_AnnAssign(
        self, original_node: AnnAssign, updated_node: AnnAssign
    ) -> Union[
        BaseSmallStatement, FlattenSentinel[BaseSmallStatement], RemovalSentinel
    ]:
        if updated_node.value is None:  # variable is declared but not assigned.
            # breakpoint()
            scope = self.get_metadata(ScopeProvider, original_node)
            if isinstance(scope, (GlobalScope, ClassScope)):
                assignments = scope.assignments[original_node.target]
                for assign in assignments:
                    # assign is the expression to which a value is assigned. To get the statement:

                    if not isinstance(assign, Assignment):
                        # concrete assignment exists elsewhere, carry on
                        return updated_node
                    assignstmt = self.get_metadata(ParentNodeProvider, assign.node)
                    if not isinstance(assignstmt, AnnAssign):
                        # different kind of assignment, which requires concrete value
                        return updated_node
                    else:
                        assn: AnnAssign = assignstmt
                        if (
                            assn.value is not None
                        ):  # conrete assignment exists elsewhere, carry on
                            return updated_node

                # okay, there are no other concrete assignments. Since it doesn't matter which we make concrete, we'll make this one
                _id = id(updated_node)
                VariableAnnotation.put(
                    _id,
                    VariableAnnotation(updated_node.target, updated_node.annotation),
                )
                newassign = AnnAssign(
                    updated_node.target.deep_clone(),
                    updated_node.annotation.deep_clone(),
                    value=parse_expression(f"VariableAnnotation.get({_id})"),
                )
                return newassign
        return updated_node


## get a single namespace equivalent to _raylet.pyx by combining all namespaces from each of the includes with _raylet
def load_raylet_namespace():
    namespaces: dict[str, dict[Optional[str], Any]] = {}
    load_namespace("ray._raylet", namespaces)
    return namespaces["ray._raylet"]


def make_module(
    name: str, attrs: dict[str, Any]
):  # make synthetic module with given name and attributes
    module = types.ModuleType(name, attrs.get("__doc__", None))
    module.__dict__.update(attrs)
    return module


# recursively load objects into the global modules (namespaces)
def load_namespace(
    namespace_name: str, namespaces: dict[str, dict[Optional[str], Any]]
):
    if namespace_name not in stub_module_dict:
        raise ImportError(f"Can't find stub module {namespace_name}")
    namespace_file = stub_module_dict[namespace_name]
    tree: MetadataWrapper = MetadataWrapper(parse_file(namespace_file))

    namespace: dict[Optional[str], Any] = {}
    namespaces[namespace_name] = namespace

    ## remove `stub-test: remove` directives
    tree = MetadataWrapper(tree.visit(RemoveIgnoredLines()))

    ## replace empty variable assignments (e.g. x:int) with the VariableAnnotation class holding annotation information
    tree = MetadataWrapper(tree.visit(EmptyAnnAssignDefaulter()))

    ## import other stub files
    tree, dependencies = IncludesImportAdaptor().extract_imports(tree)
    for module, imports in dependencies.items():
        if module == namespace_name:
            raise ImportError(
                f"Module {namespace_name} attmpting to import from itself! At locations:\n"
                + "\n".join(
                    map(
                        lambda coderange: f"{namespace_file}:{coderange.start.line}:{coderange.start.column}",
                        map(operator.itemgetter(3), imports),
                    )
                )
            )
        if module not in namespaces:
            load_namespace(module, namespaces)
        space = namespaces[module]
        for (importee, importas, importnode, coderange) in imports:

            # import *
            if importee == "*":
                all = space.get("__all__", space.keys())
                for k in all:
                    namespace[k] = space[k]
                continue

            if importee not in space:
                if importee is None:
                    space[None] = make_module(module, space)
                else:
                    raise ImportError(
                        f"Cannot import {repr(importee)} from namespace {module}; in {namespace_file}:{coderange.start.line}:{coderange.start.column}"
                    )

            importas = importas or importee or module

            namespace[importas] = space[importee]  # do an import

    ## exec this stub file
    stub_code = compile(tree.code_for_node(tree), namespace_file, "exec")
    mod = (
        {None: namespace.pop(None)} if None in namespace else {}
    )  # actually passing None as a namespace variable is probably a bad idea
    namespace["VariableAnnotation"] = VariableAnnotation
    exec(stub_code, namespace)
    namespace.update(mod)
    namespace.pop("VariableAnnotation")

    return None  # we've already updated the namespace. No return necessary


def compare_functions(stub_fn: Callable, stub_ns: dict, ray_fn: Callable, ray_ns: dict):
    pass
