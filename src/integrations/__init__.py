"""Small adapters between the preview application and file managers.

An adapter advertises actions through capabilities. The core knows only these
hooks, never file-manager names or transport details.
"""


class StandaloneIntegration:
    application_id = "io.github.space_previewer.Standalone"
    unique = False
    capabilities = frozenset()

    def __init__(self):
        self.app = None

    def register(self, connection, object_path):
        return True

    def visible_changed(self, visible):
        pass

    def parent_handle_changed(self):
        pass

    def release_startup(self):
        pass
