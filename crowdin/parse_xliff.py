import os
import json
import xml.etree.ElementTree as ET
import sys
import argparse
from typing import Dict, List, Any, Optional
from colorama import Fore, Style
from generate_shared import setup_generation, load_glossary_dict

XLIFF_NAMESPACE = {'ns': 'urn:oasis:names:tc:xliff:document:1.2'}


def validate_translations(translations: Dict[str, Any], locale: str) -> List[str]:
    """
    Validate parsed translations for a given locale.
    
    Returns a list of validation warnings/errors.
    
    TODO: Add validation rules here, such as:
    - Check for missing placeholders
    - Check for mismatched plural forms
    - Check for empty translations
    - Check for invalid characters
    - Check for consistency across locales
    """
    warnings = []
    
    # Placeholder for future validation logic
    
    return warnings


def parse_xliff_file(file_path: str, warn_on_missing_target: bool = True) -> Dict[str, Any]:
    """
    Parse a single XLIFF file and return translations as a dictionary.
    
    Args:
        file_path: Path to the XLIFF file
        warn_on_missing_target: If True, print warnings when target is missing and source is used
        
    Returns:
        Dictionary with 'translations' and 'target_language' keys
    """
    tree = ET.parse(file_path)
    root = tree.getroot()
    translations = {}

    file_elem = root.find('ns:file', namespaces=XLIFF_NAMESPACE)
    if file_elem is None:
        raise ValueError(f"Invalid XLIFF structure in file: {file_path}")

    target_language = file_elem.get('target-language')
    if target_language is None:
        raise ValueError(f"Missing target-language in file: {file_path}")

    # Handle plural groups first
    for group in root.findall('.//ns:group[@restype="x-gettext-plurals"]', namespaces=XLIFF_NAMESPACE):
        plural_forms = {}
        resname = None
        
        for trans_unit in group.findall('ns:trans-unit', namespaces=XLIFF_NAMESPACE):
            if resname is None:
                resname = trans_unit.get('resname') or trans_unit.get('id')

            target = trans_unit.find('ns:target', namespaces=XLIFF_NAMESPACE)
            source = trans_unit.find('ns:source', namespaces=XLIFF_NAMESPACE)
            context_group = trans_unit.find('ns:context-group', namespaces=XLIFF_NAMESPACE)

            if context_group is not None:
                plural_form_elem = context_group.find(
                    'ns:context[@context-type="x-plural-form"]', 
                    namespaces=XLIFF_NAMESPACE
                )
                if plural_form_elem is not None:
                    form = plural_form_elem.text.split(':')[-1].strip().lower()

                    if target is not None and target.text:
                        plural_forms[form] = target.text
                    elif source is not None and source.text:
                        plural_forms[form] = source.text
                        if warn_on_missing_target:
                            print(f"Warning: Using source text for plural form '{form}' of "
                                  f"'{resname}' in '{target_language}' as target is missing or empty")

        if resname and plural_forms:
            translations[resname] = {
                'type': 'plural',
                'forms': plural_forms
            }

    # Handle non-plural translations (skip entries already processed as plurals)
    for trans_unit in root.findall('.//ns:trans-unit', namespaces=XLIFF_NAMESPACE):
        resname = trans_unit.get('resname') or trans_unit.get('id')
        if resname is None or resname in translations:
            continue

        target = trans_unit.find('ns:target', namespaces=XLIFF_NAMESPACE)
        source = trans_unit.find('ns:source', namespaces=XLIFF_NAMESPACE)

        if target is not None and target.text:
            translations[resname] = {
                'type': 'string',
                'value': target.text
            }
        elif source is not None and source.text:
            translations[resname] = {
                'type': 'string',
                'value': source.text
            }
            if warn_on_missing_target:
                print(f"Warning: Using source text for '{resname}' in "
                      f"'{target_language}' as target is missing or empty")

    return {
        'translations': translations,
        'target_language': target_language
    }


def parse_all_xliff_files(input_directory: str) -> Dict[str, Any]:
    """
    Parse all XLIFF files in the input directory and return a combined result.
    
    Args:
        input_directory: Directory containing XLIFF files and project info
        
    Returns:
        Dictionary containing all parsed data ready for platform-specific generators
    """
    setup_values = setup_generation(input_directory)
    source_language = setup_values['source_language']
    rtl_languages = setup_values['rtl_languages']
    non_translatable_strings_file = setup_values['non_translatable_strings_file']
    target_languages = setup_values['target_languages']
    
    glossary_dict = load_glossary_dict(non_translatable_strings_file)
    
    all_languages = [source_language] + target_languages
    parsed_locales = {}
    all_warnings = []
    
    for language in all_languages:
        lang_locale = language['locale']
        input_file = os.path.join(input_directory, f"{lang_locale}.xliff")
        
        if not os.path.exists(input_file):
            raise FileNotFoundError(f"Could not find '{input_file}' in raw translations directory")
        
        print(f"\033[2K{Fore.WHITE}⏳ Parsing {lang_locale}...{Style.RESET_ALL}", end='\r')
        
        try:
            result = parse_xliff_file(input_file)
            translations = result['translations']
            target_language = result['target_language']
            
            # Run validation
            warnings = validate_translations(translations, lang_locale)
            if warnings:
                all_warnings.extend([(lang_locale, w) for w in warnings])
            
            parsed_locales[lang_locale] = {
                'target_language': target_language,
                'translations': translations,
                'language_info': language
            }
            
        except Exception as e:
            raise ValueError(f"Error processing locale {lang_locale}: {str(e)}")
    
    print(f"\033[2K{Fore.GREEN}✅ Parsed {len(parsed_locales)} locale files{Style.RESET_ALL}")
    
    # Print any validation warnings
    if all_warnings:
        print(f"{Fore.YELLOW}⚠️  Validation warnings:{Style.RESET_ALL}")
        for locale, warning in all_warnings:
            print(f"  [{locale}] {warning}")
    
    return {
        'source_language': source_language,
        'target_languages': target_languages,
        'rtl_languages': rtl_languages,
        'glossary': glossary_dict,
        'locales': parsed_locales
    }


def main():
    parser = argparse.ArgumentParser(
        description='Parse XLIFF translation files into an intermediate JSON format'
    )
    parser.add_argument(
        'raw_translations_directory',
        help='Directory which contains the raw translation files'
    )
    parser.add_argument(
        'output_file',
        help='Path to save the parsed translations JSON file'
    )
    args = parser.parse_args()
    
    try:
        result = parse_all_xliff_files(args.raw_translations_directory)
        
        # Write output
        os.makedirs(os.path.dirname(args.output_file) or '.', exist_ok=True)
        with open(args.output_file, 'w', encoding='utf-8') as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
        
        print(f"{Fore.GREEN}✅ Parsed translations saved to {args.output_file}{Style.RESET_ALL}")
        
    except KeyboardInterrupt:
        print("\nProcess interrupted by user")
        sys.exit(0)
    except Exception as e:
        print(f"\033[2K{Fore.RED}❌ An error occurred: {str(e)}{Style.RESET_ALL}")
        sys.exit(1)


if __name__ == "__main__":
    main()
