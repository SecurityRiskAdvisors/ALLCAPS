import tempfile
from pathlib import Path
import desert
import yaml
from typing import get_args
from dataclasses import fields, MISSING


def gen_rand_dir() -> Path:
    """
    Generate a temp directory
    """
    dir_name = tempfile.mkdtemp()
    return Path(dir_name)


class FileLoaderMixin:
    """
    Mixin to allow loading a class from a YAML file. Data is validated using marshmallow.
    """

    @property
    def file_path(self) -> Path:
        return self.__original_file_path

    @file_path.setter
    def file_path(self, v):
        self.__original_file_path = v

    @classmethod
    def from_dict(cls, dict_):
        return desert.schema(cls).load(dict_)

    @classmethod
    def from_file(cls, file: Path | str):
        file_path = file.resolve() if isinstance(file, Path) else Path(file).resolve()
        file_str = file_path.read_text()
        file_yml = yaml.safe_load(file_str)
        instance = cls.from_dict(file_yml)
        instance.file_path = file_path
        return instance


def fixup_dc_factory_fields(instance):
    """
    This function will change a dataclass instance's attribute
    values to be their default factory value if the attribute
    is None and is an optional attribute.
    This is meant to be used on dataclasses loaded with desert since
    it does not properly call default factories for optional fields
    """

    for cls_field in fields(instance):
        if (
            # check if field is optional
            type(None) in get_args(cls_field.type)
            and
            # check that the current value is None
            getattr(instance, cls_field.name) is None
            and
            # check that there is a default factory
            cls_field.default_factory != MISSING
        ):
            # if all are true, then set the value to be the default factory
            setattr(instance, cls_field.name, cls_field.default_factory())
