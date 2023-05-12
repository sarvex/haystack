import logging
from pathlib import Path
from typing import List, Optional, Dict, Any
from collections import defaultdict
import json
import copy
from azure.ai.formrecognizer import DocumentAnalysisClient, AnalyzeResult
from azure.core.credentials import AzureKeyCredential

from haystack.nodes.file_converter import BaseConverter

logger = logging.getLogger(__name__)


class AzureConverter(BaseConverter):
    """
    File converter that makes use of Microsoft Azure's Form Recognizer service
    (https://azure.microsoft.com/en-us/services/form-recognizer/).
    This Converter extracts both text and tables.
    Supported file formats are: PDF, JPEG, PNG, BMP and TIFF.

    In order to be able to use this Converter, you need an active Azure account
    and a Form Recognizer or Cognitive Services resource.
    (Here you can find information on how to set this up:
    https://docs.microsoft.com/en-us/azure/applied-ai-services/form-recognizer/quickstarts/try-v3-python-sdk#prerequisites)

    """

    def __init__(
        self,
        endpoint: str,
        credential_key: str,
        model_id: str = "prebuilt-document",
        valid_languages: Optional[List[str]] = None,
        save_json: bool = False,
        preceding_context_len: int = 3,
        following_context_len: int = 3,
        merge_multiple_column_headers: bool = True,
    ):
        """
        :param endpoint: Your Form Recognizer or Cognitive Services resource's endpoint.
        :param credential_key: Your Form Recognizer or Cognitive Services resource's subscription key.
        :param model_id: The identifier of the model you want to use to extract information out of your file.
                         Default: "prebuilt-document". General purpose models are "prebuilt-document"
                         and "prebuilt-layout".
                         List of available prebuilt models:
                         https://azuresdkdocs.blob.core.windows.net/$web/python/azure-ai-formrecognizer/3.2.0b1/index.html#documentanalysisclient
        :param valid_languages: Validate languages from a list of languages specified in the ISO 639-1
                                (https://en.wikipedia.org/wiki/ISO_639-1) format.
                                This option can be used to add test for encoding errors. If the extracted text is
                                not one of the valid languages, then it might likely be encoding error resulting
                                in garbled text.
        :param save_json: Whether to save the output of the Form Recognizer to a JSON file.
        :param preceding_context_len: Number of lines before a table to extract as preceding context (will be returned as part of meta data).
        :param following_context_len: Number of lines after a table to extract as subsequent context (will be returned as part of meta data).
        :param merge_multiple_column_headers: Some tables contain more than one row as a column header (i.e., column description).
                                              This parameter lets you choose, whether to merge multiple column header
                                              rows to a single row.
        """
        # save init parameters to enable export of component config as YAML
        self.set_config(
            endpoint=endpoint,
            credential_key=credential_key,
            model_id=model_id,
            valid_languages=valid_languages,
            save_json=save_json,
            preceding_context_len=preceding_context_len,
            following_context_len=following_context_len,
            merge_multiple_column_headers=merge_multiple_column_headers,
        )

        self.document_analysis_client = DocumentAnalysisClient(
            endpoint=endpoint, credential=AzureKeyCredential(credential_key)
        )
        self.model_id = model_id
        self.valid_languages = valid_languages
        self.save_json = save_json
        self.preceding_context_len = preceding_context_len
        self.following_context_len = following_context_len
        self.merge_multiple_column_headers = merge_multiple_column_headers

        super().__init__(valid_languages=valid_languages)

    def convert(
        self,
        file_path: Path,
        meta: Optional[Dict[str, str]] = None,
        remove_numeric_tables: Optional[bool] = None,
        valid_languages: Optional[List[str]] = None,
        encoding: Optional[str] = "utf-8",
        pages: Optional[str] = None,
        known_language: Optional[str] = None,
    ) -> List[Dict[str, Any]]:

        """
        Extract text and tables from a PDF, JPEG, PNG, BMP or TIFF file using Azure's Form Recognizer service.

        :param file_path: Path to the file you want to convert.
        :param meta: Optional dictionary with metadata that shall be attached to all resulting documents.
                     Can be any custom keys and values.
        :param remove_numeric_tables: Not applicable.
        :param valid_languages: Validate languages from a list of languages specified in the ISO 639-1
                                (https://en.wikipedia.org/wiki/ISO_639-1) format.
                                This option can be used to add test for encoding errors. If the extracted text is
                                not one of the valid languages, then it might likely be encoding error resulting
                                in garbled text.
        :param encoding: Not applicable.
        :param pages: Custom page numbers for multi-page documents(PDF/TIFF). Input the page numbers and/or ranges
                      of pages you want to get in the result. For a range of pages, use a hyphen,
                      like pages=”1-3, 5-6”. Separate each page number or range with a comma.
        :param known_language: Locale hint of the input document.
                               See supported locales here: https://aka.ms/azsdk/formrecognizer/supportedlocales.
        """
        if isinstance(file_path, str):
            file_path = Path(file_path)

        if valid_languages is None:
            valid_languages = self.valid_languages

        with open(file_path, "rb") as file:
            poller = self.document_analysis_client.begin_analyze_document(
                self.model_id, file, pages=pages, locale=known_language
            )
            result = poller.result()

        if self.save_json:
            with open(file_path.with_suffix(".json"), "w") as json_file:
                json.dump(result.to_dict(), json_file, indent=2)

        return self._convert_tables_and_text(result, meta, valid_languages, file_path)

    def convert_azure_json(
        self,
        file_path: Path,
        meta: Optional[Dict[str, str]] = None,
        valid_languages: Optional[List[str]] = None,
    ) -> List[Dict[str, Any]]:
        """
        Extract text and tables from the JSON output of Azure's Form Recognizer service.

        :param file_path: Path to the JSON-file you want to convert.
        :param meta: Optional dictionary with metadata that shall be attached to all resulting documents.
                     Can be any custom keys and values.
        :param valid_languages: Validate languages from a list of languages specified in the ISO 639-1
                                (https://en.wikipedia.org/wiki/ISO_639-1) format.
                                This option can be used to add test for encoding errors. If the extracted text is
                                not one of the valid languages, then it might likely be encoding error resulting
                                in garbled text.
        """
        if valid_languages is None:
            valid_languages = self.valid_languages

        with open(file_path) as azure_file:
            azure_result = json.load(azure_file)
            azure_result = AnalyzeResult.from_dict(azure_result)

        return self._convert_tables_and_text(
            azure_result, meta, valid_languages, file_path
        )

    def _convert_tables_and_text(
        self,
        result: AnalyzeResult,
        meta: Optional[Dict[str, str]],
        valid_languages: Optional[List[str]],
        file_path: Path,
    ) -> List[Dict[str, Any]]:
        tables = self._convert_tables(result, meta)
        text = self._convert_text(result, meta)
        docs = tables + [text]

        if valid_languages:
            file_text = text["content"] + " ".join(
                [cell for table in tables for row in table["content"] for cell in row]
            )
            if not self.validate_language(file_text, valid_languages):
                logger.warning(
                    f"The language for {file_path} is not one of {valid_languages}. The file may not have "
                    f"been decoded in the correct text format."
                )

        return docs

    def _convert_tables(self, result: AnalyzeResult, meta: Optional[Dict[str, str]]) -> List[Dict[str, Any]]:
        converted_tables = []

        for table in result.tables:
            # Initialize table with empty cells
            table_list = [[""] * table.column_count for _ in range(table.row_count)]
            additional_column_header_rows = set()
            caption = ""
            row_idx_start = 0

            for idx, cell in enumerate(table.cells):
                # Remove ':selected:'/':unselected:' tags from cell's content
                cell.content = cell.content.replace(":selected:", "")
                cell.content = cell.content.replace(":unselected:", "")

                # Check if first row is a merged cell spanning whole table
                # -> exclude this row and use as a caption
                if idx == 0 and cell.column_span == table.column_count:
                    caption = cell.content
                    row_idx_start = 1
                    table_list.pop(0)
                    continue

                for c in range(cell.column_span):
                    for r in range(cell.row_span):
                        if (
                            self.merge_multiple_column_headers
                            and cell.kind == "columnHeader"
                            and cell.row_index > row_idx_start
                        ):
                            # More than one row serves as column header
                            table_list[0][cell.column_index + c] += f"\n{cell.content}"
                            additional_column_header_rows.add(cell.row_index - row_idx_start)
                        else:
                            table_list[cell.row_index + r - row_idx_start][cell.column_index + c] = cell.content

            # Remove additional column header rows, as these got attached to the first row
            for row_idx in sorted(additional_column_header_rows, reverse=True):
                del table_list[row_idx]

            # Get preceding context of table
            table_beginning_page = next(
                page for page in result.pages if page.page_number == table.bounding_regions[0].page_number
            )
            table_start_offset = table.spans[0].offset
            preceding_lines = [
                line.content for line in table_beginning_page.lines if line.spans[0].offset < table_start_offset
            ]
            preceding_context = "\n".join(preceding_lines[-self.preceding_context_len :]) + f"\n{caption}"
            preceding_context = preceding_context.strip()

            # Get following context
            table_end_page = (
                table_beginning_page
                if len(table.bounding_regions) == 1
                else next(page for page in result.pages if page.page_number == table.bounding_regions[-1].page_number)
            )
            table_end_offset = table_start_offset + table.spans[0].length
            following_lines = [line.content for line in table_end_page.lines if line.spans[0].offset > table_end_offset]
            following_context = "\n".join(following_lines[: self.following_context_len])

            table_meta = copy.deepcopy(meta)

            if isinstance(table_meta, dict):
                table_meta["preceding_context"] = preceding_context
                table_meta["following_context"] = following_context
            else:
                table_meta = {"preceding_context": preceding_context, "following_context": following_context}
            converted_tables.append({"content": table_list, "content_type": "table", "meta": table_meta})

        return converted_tables

    def _convert_text(self, result: AnalyzeResult, meta: Optional[Dict[str, str]]) -> Dict[str, Any]:
        text = ""
        table_spans_by_page = defaultdict(list)
        for table in result.tables:
            table_spans_by_page[table.bounding_regions[0].page_number].append(table.spans[0])

        for page in result.pages:
            tables_on_page = table_spans_by_page[page.page_number]
            for line in page.lines:
                in_table = any(
                    table.offset
                    <= line.spans[0].offset
                    <= table.offset + table.length
                    for table in tables_on_page
                )
                if in_table:
                    continue
                text += f"{line.content}\n"
            text += "\f"

        return {"content": text, "content_type": "text", "meta": meta}
