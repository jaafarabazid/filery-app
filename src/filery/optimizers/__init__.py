"""File optimizers, one module per media type.

PDF is the first. Images, video and format conversion are meant to slot in here
as sibling modules exposing the same shape (a set of Profiles and an optimize()
function), so the app and CLI can stay type-agnostic.
"""

from . import pdf

# Maps a lowercased file extension to the module that handles it.
REGISTRY = {
    ".pdf": pdf,
}


def optimizer_for(path: str):
    import os
    return REGISTRY.get(os.path.splitext(path)[1].lower())
