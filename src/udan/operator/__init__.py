"""udan.operator: the operators engine as a core subpackage.

The walk every operator kind's operators go through lives here (plugins_operator
provides it as the OperatorsEngineAPI service); the kind-blind vocabulary it walks
lives in the core contract (udan.core.api_operators) so a plugin - the query parser among
them - can speak it too. The operator kinds live beside the engine as its plugin modules -
plugins_operator_inserter, plugins_operator_filter, plugins_operator_extender,
plugins_operator_grouper, plugins_operator_mapper, plugins_operator_replacer,
plugins_operator_sorter - each registering its applicator into this engine's dispatch
at container build.
"""
