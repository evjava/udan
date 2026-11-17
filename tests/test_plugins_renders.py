"""Tests for render tools."""

from tests.conftest import make_qp, register_tools_from_module
from udan.plugins_tools_examples import plugins_fs
from udan.plugins_tools_examples.plugins_org import render_org_images
from udan.renders.plugins_renders import render_term_list_item


def test_render_org_images_with_png(tmp_path):
    """Test render_org_images with PNG file."""
    image_file = tmp_path / "test.png"
    image_file.write_text("fake png content")

    result = render_org_images(image_file)
    lines = result.split("\n")

    assert len(lines) == 2
    assert lines[0] == f"** {image_file}"
    assert lines[1] == f"[[{image_file}]]"


def test_render_org_images_with_jpeg(tmp_path):
    """Test render_org_images with JPEG file."""
    image_file = tmp_path / "photo.jpeg"
    image_file.write_text("fake jpeg content")

    result = render_org_images(image_file)
    lines = result.split("\n")

    assert len(lines) == 2
    assert "photo.jpeg" in result
    assert f"[[{image_file}]]" in result


def test_render_org_images_with_svg(tmp_path):
    """Test render_org_images with SVG file."""
    svg_file = tmp_path / "diagram.svg"
    svg_file.write_text("<svg></svg>")

    result = render_org_images(svg_file)

    assert "** " in result
    assert "[[" in result
    assert "diagram.svg" in result


def test_render_org_images_with_string_path(tmp_path):
    """Test render_org_images with string path instead of Path object."""
    image_file = tmp_path / "image.png"
    image_file.write_text("fake content")

    result = render_org_images(str(image_file))

    assert "** " in result
    assert "[[" in result
    assert "image.png" in result


def test_render_org_images_with_non_image(tmp_path):
    """Test render_org_images with non-image file (falls back to org format)."""
    text_file = tmp_path / "document.txt"
    text_file.write_text("text content")

    result = render_org_images(text_file)

    # Should use default org format, not image format
    assert result == f"- {text_file}"
    assert "[[" not in result


def test_render_org_images_with_unsupported_extension(tmp_path):
    """Test render_org_images with unsupported file extension."""
    data_file = tmp_path / "data.json"
    data_file.write_text("{}")

    result = render_org_images(data_file)

    # Should use default org format
    assert result == f"- {data_file}"


def test_render_org_images_with_uppercase_extension(tmp_path):
    """Test render_org_images with uppercase extension (JPG)."""
    image_file = tmp_path / "photo.JPG"
    image_file.write_text("fake content")

    result = render_org_images(image_file)

    # Should still recognize as image
    assert "** " in result
    assert "[[" in result


def test_render_org_images_with_query(tmp_path, make_ctx):
    """Test render_org_images through query execution with files."""
    # Create test images
    image1 = tmp_path / "photo1.png"
    image1.write_text("fake png 1")
    image2 = tmp_path / "photo2.jpg"
    image2.write_text("fake jpeg")

    ctx = make_ctx()
    qp = make_qp(ctx)
    register_tools_from_module(ctx, render_org_images.__module__)

    # Query: list files and render with :images
    # Note: using insert_ls_files from plugins_fs
    register_tools_from_module(ctx, plugins_fs.__name__)

    forest, attrs, render_specs, out = qp.execute_query(f"insert_ls_files {tmp_path}, :images")

    # Should show images with org-mode inline format
    # Check line-by-line for exact format
    lines = out.strip().split("\n")
    assert len(lines) == 4  # 2 images × 2 lines each

    # Each image should have: "** <path>" followed by "[[<path>]]"
    # Extract the base names (without path) from the "**" lines
    heading_lines = [line for line in lines if line.startswith("** ")]
    link_lines = [line for line in lines if line.startswith("[[")]

    assert len(heading_lines) == 2
    assert len(link_lines) == 2

    # Check that both filenames are present in the headings
    heading_names = [line.split("/")[-1] for line in heading_lines]
    assert "photo1.png" in heading_names
    assert "photo2.jpg" in heading_names

    # Check that link lines match their corresponding heading lines
    for i, heading in enumerate(heading_lines):
        path = heading[3:]  # Remove "** " prefix
        assert link_lines[i] == f"[[{path}]]"


def test_render_term_list_item_with_depth():
    """Test that render_term_list_item uses depth for proper indentation.

    Depth 0 should have no indent, depth 1 should have 2 spaces, depth 2 should have 4 spaces, etc.
    """

    # Test depth 0 (no indent)
    result_depth_0 = render_term_list_item("item1", depth=0)
    assert result_depth_0 == "- item1"

    # Test depth 1 (2 spaces)
    result_depth_1 = render_term_list_item("item2", depth=1)
    assert result_depth_1 == "  - item2"

    # Test depth 2 (4 spaces)
    result_depth_2 = render_term_list_item("item3", depth=2)
    assert result_depth_2 == "    - item3"

    # Test depth 3 (6 spaces)
    result_depth_3 = render_term_list_item("item4", depth=3)
    assert result_depth_3 == "      - item4"


def test_render_term_list_item_with_attrs():
    """Test that render_term_list_item with attributes shows :: separator."""

    # Test with attrs dict
    attrs = {"attr1": "value1", "attr2": "value2"}
    result = render_term_list_item("item1", depth=0, attrs=attrs)
    # Should use first attribute value
    assert result == "- item1 :: value1"

    # Test with nested item dict
    item_dict = {"item": "item2", "attrs": {"nested_attr": "nested_value"}}
    result = render_term_list_item(item_dict, depth=1)
    assert result == "  - item2 :: nested_value"
