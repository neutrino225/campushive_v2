from typing import Dict, Any
from ..nodes.student import student_router_node

# Thin wrapper to expose student graph node

def get_student_node() -> Dict[str, Any]:
    return {"node": student_router_node}
