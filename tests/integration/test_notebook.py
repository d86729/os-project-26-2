"""Execute the initial smoke notebook with a fresh real kernel, not mocked cells."""
import json
from pathlib import Path
import sys
import nbformat
from nbclient import NotebookClient

ROOT=Path(__file__).resolve().parents[2]


def test_initial_notebook_clean_kernel():
    notebook=nbformat.read(ROOT/'notebooks/submission.ipynb',as_version=4)
    for cell in notebook.cells:
        if cell.cell_type=='code':
            assert '# 담당: 김대건' in cell.source
            assert not cell.get('outputs') and cell.get('execution_count') is None
    client=NotebookClient(notebook,timeout=300,kernel_name='protection-study',
                          resources={'metadata':{'path':str(ROOT)}})
    executed=client.execute()
    output=ROOT/'results/validation/submission-executed.ipynb'
    nbformat.write(executed,output)
    errors=[o for c in executed.cells if c.cell_type=='code' for o in c.outputs if o.output_type=='error']
    assert not errors
    texts='\n'.join(o.get('text','') for c in executed.cells if c.cell_type=='code' for o in c.outputs)
    assert 'not_implemented' in texts
    assert 'NOTEBOOK_SMOKE_VERIFIED' in texts
    report={'status':'passed','kernel':'protection-study','python':sys.executable,
            'notebook':'notebooks/submission.ipynb','executed_notebook':str(output.relative_to(ROOT)),
            'code_cells':sum(c.cell_type=='code' for c in executed.cells),
            'errors':errors,'scope':'initial smoke only; members not implemented; no main experiments'}
    (ROOT/'results/validation/notebook.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
