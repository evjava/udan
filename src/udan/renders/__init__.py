"""udan.renders: the renders domain.

Everything that produces output lives here: the render kind, the render
tools, the engine that renders a forest through them, and the tabular
renders beside them. The core names the output seam only (udan.core.api_output_engine)
- this package's container contribution answers it with the render engine, and
decorates the type system with the ranked render suggestions. It depends on
udan.attributes: rendering reads attribute values from the store that
package owns.

The package is part of udan, so Plugins discovers it on every boot the way it
discovers udan.operator* and udan.attributes. A container built without this
package's provider - a bare IOC() in a test - keeps the core's fallback: the
output step answers with the advice that says what is missing, the chain still
applies, values are still computed, nothing turns the forest into text.
"""
