from scripts.check_foundation_contracts import (
    test_json_schemas_parse,
    test_required_foundation_files_exist,
    test_required_foundation_terms_present,
)


def test_foundation_contracts_exist() -> None:
    test_required_foundation_files_exist()


def test_foundation_contracts_include_required_terms() -> None:
    test_required_foundation_terms_present()


def test_foundation_contract_json_schemas_parse() -> None:
    test_json_schemas_parse()
