/*
 * A KBase module: kb_GRIN
 */
module kb_GRIN {
    typedef string workspace_name;
    typedef string ws_ref; /* generic workspace object reference */

    typedef structure {
        workspace_name workspace_name;
        ws_ref feature_set_ref;           /* KBaseCollections.FeatureSet */
        string multiplex_rdata_path;      /* still a staging file */
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
