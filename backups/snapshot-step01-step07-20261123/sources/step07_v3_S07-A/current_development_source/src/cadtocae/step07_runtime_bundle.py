"""Bundle reachable functions without changing their source or execution order."""
import ast

def bundle_runtime(sources, entry="p7_run"):
    functions={};chunks=[];imports=[];raw_lines=0
    for filename,source in sources:
        tree=ast.parse(source,filename=filename);lines=source.splitlines(True);raw_lines+=len(lines)
        for node in tree.body:
            if isinstance(node,ast.FunctionDef):
                if node.name in functions:raise ValueError('RUNTIME_DUPLICATE_FUNCTION: '+node.name)
                functions[node.name]=(node, ''.join(lines[node.lineno-1:node.end_lineno]))
            elif isinstance(node,(ast.Import,ast.ImportFrom)):
                text=''.join(lines[node.lineno-1:node.end_lineno])
                if text not in imports:imports.append(text)
            elif isinstance(node,ast.Expr) and isinstance(node.value,ast.Constant) and isinstance(node.value.value,str):pass
            else:raise ValueError('UNREVIEWED_RUNTIME_TOP_LEVEL: '+filename+':'+str(node.lineno))
    reachable=set();pending=[entry]
    while pending:
        name=pending.pop()
        if name in reachable:continue
        reachable.add(name)
        for node in ast.walk(functions[name][0]):
            if isinstance(node,ast.Name) and node.id in functions and node.id not in reachable:pending.append(node.id)
    for name,(_,source) in functions.items():
        if name in reachable:chunks.append(source)
    result='# -*- coding: utf-8 -*-\n# Generated from shared runtime; sole entry: '+entry+'.\n'+'\n'.join(imports+chunks)+'\n'
    audit=dict(original_lines=raw_lines,bundled_lines=len(result.splitlines()),removed_functions=sorted(set(functions)-reachable),
               retained_functions=sorted(reachable),duplicate_functions=[],
               intentional_rebinding='p7_precise_tie_geometry replaces t4_faces/t4_inverse with verified Step04 transforms')
    return result,audit
