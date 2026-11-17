"""udan.plugins_tools_core: the core's own introspection plugins.

``plugins_system`` is the module here: the ``udan_config``, ``udan_plugins_deps``,
``udan_ioc_deps``, ``introspect_tool``, ``render_help`` and ``vars`` tools - the family
that reads the container, the registry and the plugins snapshot instead of processing
a forest. ``plugins_help`` holds the listing that answers the ``?`` questions
(``help``, ``help_list``). The package lives in a package of its own so the
plugin-module scan (``plugins_*.py``) finds it beside the other plugin families:
``udan.plugins_tools_examples`` (the built-in tool families) and ``udan.plugins_tools_demo`` (the demo
inserters).
"""
