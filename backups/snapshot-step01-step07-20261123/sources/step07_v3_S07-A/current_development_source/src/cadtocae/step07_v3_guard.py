"""Release isolation: never write to original Step07/Step02-06 projects."""
from pathlib import Path
def protect_output(path):
 p=Path(path).resolve()
 for parent in (p,)+tuple(p.parents):
  name=parent.name.lower()
  if name=='cadtocae-step07-development' or name.startswith('cadtocae-feature-step'):
   raise ValueError('ORIGINAL_PROJECT_IS_READ_ONLY: '+str(p))
