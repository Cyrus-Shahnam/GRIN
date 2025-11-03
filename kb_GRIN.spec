/*
 * A KBase module: kb_GRIN
 */

module kb_GRIN {
    typedef string workspace_name;
    typedef string file_path;

    typedef structure {
        workspace_name workspace_name;
        file_path geneset_tsv_path;
        file_path multiplex_rdata_path;
        float restart;
        string tau_csv;
        string run_label;
        int verbosity;
        int plot;
        int simple_filenames;
        string output_name;
    } RunGRINParams;

    typedef structure {
        string report_name;
        string report_ref;
    } ReportResults;

    funcdef run_grin(RunGRINParams params) returns (ReportResults);
};
