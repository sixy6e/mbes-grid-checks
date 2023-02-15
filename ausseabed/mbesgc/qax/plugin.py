from typing import List, Dict, NoReturn, Callable, Tuple
from pathlib import Path


from ausseabed.mbesgc.lib.allchecks import all_checks
from ausseabed.mbesgc.lib.data import get_input_details, \
    inputs_from_qajson_checks
from ausseabed.mbesgc.lib.executor import Executor

from hyo2.qax.lib.plugin import QaxCheckToolPlugin, QaxCheckReference, \
    QaxFileType
from ausseabed.qajson.model import QajsonRoot, QajsonDataLevel, QajsonCheck, \
    QajsonFile, QajsonInputs


class MbesGridChecksQaxPlugin(QaxCheckToolPlugin):

    # supported raw data file types
    file_types = [
        QaxFileType(
            name="GeoTIFF",
            extension="tiff",
            group="Survey DTMs",
            icon="tif.png"
        ),
        QaxFileType(
            name="GeoTIFF",
            extension="tif",
            group="Survey DTMs",
            icon="tif.png"
        ),
        QaxFileType(
            name="BAG file",
            extension="bag",
            group="Survey DTMs",
            icon="bag.png"
        ),
    ]

    def __init__(self):
        super(MbesGridChecksQaxPlugin, self).__init__()
        # name of the check tool
        self.name = 'MBES Grid Checks'
        self._check_references = self._build_check_references()

        self.exe = None

    def _build_check_references(self) -> List[QaxCheckReference]:
        data_level = "survey_products"
        check_refs = []

        # loop through each check class, defining the QaxCheckRefs
        for mgc_check_class in all_checks:
            cr = QaxCheckReference(
                id=mgc_check_class.id,
                name=mgc_check_class.name,
                data_level=data_level,
                description=None,
                supported_file_types=MbesGridChecksQaxPlugin.file_types,
                default_input_params=mgc_check_class.input_params,
                version=mgc_check_class.version,
            )
            check_refs.append(cr)

        return check_refs

    def checks(self) -> List[QaxCheckReference]:
        return self._check_references

    def __check_files_match(self, a: QajsonInputs, b: QajsonInputs) -> bool:
        """ Checks if the input files in a are the same as b. This is used
        to match the plugin's output with the QAJSON outputs that must be
        updated with the check results.
        """
        set_a = set([str(p.path) for p in a.files])
        set_b = set([str(p.path) for p in b.files])
        return set_a == set_b

    def get_summary_details(self) -> List[Tuple[str, str]]:
        return [
            ("header", "Number of Nodes"),
            ("DENSITY", "Number of Nodes with density Fails"),
            ("DENSITY", r"% of nodes with 5 soundings or greater"),
        ]

    def get_summary_value(
            self,
            field_section: str,
            field_name: str,
            filename: str,
            qajson: QajsonRoot
        ) -> object:
        """
        """
        checks = self._get_qajson_checks(qajson)
        file_checks = self._checks_filtered_by_file(filename, checks)
        if field_section == 'header' and field_name == "Number of Nodes":
            return "non"
        else:
            return 0


    def run(
            self,
            qajson: QajsonRoot,
            progress_callback: Callable = None,
            qajson_update_callback: Callable = None,
            is_stopped: Callable = None
    ) -> NoReturn:
        grid_data_checks = qajson.qa.survey_products.checks
        ifd_list = inputs_from_qajson_checks(grid_data_checks)

        self.exe = Executor(ifd_list, all_checks)

        # set options coming from QAX
        self.exe.spatial_qajson = self.spatial_outputs_qajson
        self.exe.spatial_export = self.spatial_outputs_export
        self.exe.spatial_export_location = self.spatial_outputs_export_location

        # the check_runner callback accepts only a float, whereas the qax
        # qwax plugin check tool callback requires a referece to a check tool
        # AND a progress value. Hence this little mapping function,
        def pg_call(check_runner_progress):
            progress_callback(self, check_runner_progress)

        self.exe.run(pg_call, qajson_update_callback, is_stopped)

        for (ifd, check_id), check in self.exe.check_result_cache.items():
            check_outputs = check.get_outputs()

            ifd.qajson_check.outputs = check_outputs

        # MBESGC runs all checks over each tile of an input file, therefore
        # it's only possible to update the qajson once all checks have been
        # completed.
        if qajson_update_callback is not None:
            qajson_update_callback()

        # # the checks runner produces an array containing a listof checks
        # # each check being a dictionary. Deserialise these using the qa json
        # # datalevel class
        # out_dl = QajsonDataLevel.from_dict(
        #     {'checks': self.check_runner.output})
        #
        # # now loop through all raw_data (Mate only does raw data) checks in
        # # the qsjson and update the right checks with the check runner output
        # for out_check in out_dl.checks:
        #     # find the check definition in the input qajson.
        #     # note: both check and id must match. The same check implmenetation
        #     # may be include twice but with diffferent names (this is
        #     # supported)
        #     in_check = next(
        #         (
        #             c
        #             for c in qajson.qa.raw_data.checks
        #             if (
        #                 c.info.id == out_check.info.id and
        #                 c.info.name == out_check.info.name and
        #                 self.__check_files_match(c.inputs, out_check.inputs))
        #         ),
        #         None
        #     )
        #     if in_check is None:
        #         # this would indicate a check was run that was not included
        #         # in the input qajson. *Should never occur*
        #         raise RuntimeError(
        #             "Check {} ({}) found in output that was not "
        #             "present in input"
        #             .format(out_check.info.name, out_check.info.id))
        #     # replace the input qajson check outputs with the output generated
        #     # by the check_runner
        #     in_check.outputs = out_check.outputs

    def update_qa_json_input_files(
            self, qa_json: QajsonRoot, files: List[Path]) -> NoReturn:
        """ Updates qa_json to support the list of provided files. function
        defined in base class has been overwritten to support some MBES GC
        specifics in the way it supports multiple files.
        """
        # when this function has been called qa_json has been updated to
        # include the list of checks. While Mate will support processing of
        # multiple files within one QA JSON check definition, the QA JSON
        # schema doesn't support multiple outputs per check. To work around
        # this, this function take the specified checks, and adds one check
        # definition per file. Each Mate check is therefore run with a single
        # input file, but the same check is duplicated for each file passed in
        all_data_levels = [check_ref.data_level for check_ref in self.checks()]
        all_data_levels = list(set(all_data_levels))

        # build a list of GC checks in the qa_json for all the different data
        # levels (this really only needs to check the raw_data data level)
        all_mgc_checks = []
        for dl in all_data_levels:
            dl_sp = getattr(qa_json.qa, dl)
            if dl_sp is None:
                continue
            for check in dl_sp.checks:
                if self.get_check_reference(check.info.id) is not None:
                    all_mgc_checks.append(check)

        # now remove the current mgc definitions as we'll add these all back
        # in again for each input file.
        for mgc_check in all_mgc_checks:
            for dl in all_data_levels:
                dl_sp = getattr(qa_json.qa, dl)
                dl_sp.checks.remove(mgc_check)

        for (input_file, input_file_group) in files:
            for mgc_check in all_mgc_checks:
                check_ref = self.get_check_reference(mgc_check.info.id)
                if not check_ref.supports_file(input_file, input_file_group):
                    continue
                mgc_check_clone = QajsonCheck.from_dict(mgc_check.to_dict())
                inputs = mgc_check_clone.get_or_add_inputs()
                inputs.files.append(
                    QajsonFile(
                        path=str(input_file),
                        file_type=input_file_group,
                        description=None
                    )
                )
                # ** ASSUME ** mgc checks only go in the survey_products
                # data level
                qa_json.qa.survey_products.checks.append(mgc_check_clone)
