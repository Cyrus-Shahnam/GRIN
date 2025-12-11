# -*- coding: utf-8 -*-
#BEGIN_HEADER
import os
import uuid
import shlex
import subprocess

from installed_clients.DataFileUtilClient import DataFileUtil
from installed_clients.KBaseReportClient import KBaseReport

# Call R via micromamba 'grin' env
RSCRIPT = "/usr/local/bin/micromamba run -n grin Rscript"
GRIN_R  = "/opt/GRIN/R/GRIN.R"
#END_HEADER


class kb_GRIN:
    '''
    Module Name:
    kb_GRIN

    Module Description:
    Wrap GRIN (R) to refine a gene set against a multiplex network.
    '''

    ######## WARNING FOR GEVENT USERS ####### noqa
    # Since asynchronous IO can lead to methods - even the same method -
    # interrupting each other, you must be *very* careful when using global
    # state. A method could easily clobber the state set by another while
    # the latter method is running.
    ######################################### noqa
    VERSION = "0.0.1"
    GIT_URL = "https://github.com/Cyrus-Shahnam/GRIN.git"
    GIT_COMMIT_HASH = "969b835d9cd10d5b536a56b48c4efe2341671f85"

    #BEGIN_CLASS_HEADER
    #END_CLASS_HEADER

    def __init__(self, config):
        #BEGIN_CONSTRUCTOR
        self.scratch = os.path.abspath(config['scratch'])
        self.callback_url = os.environ.get('SDK_CALLBACK_URL')
        if not self.callback_url:
            raise RuntimeError("SDK_CALLBACK_URL not set in environment")
        self.dfu = DataFileUtil(self.callback_url)
        self.kbr = KBaseReport(self.callback_url)
        #END_CONSTRUCTOR
        pass

    #BEGIN_CLASS_METHODS
    def _run_cmd(self, cmd):
        print(f"[kb_GRIN] run: {cmd}")
        p = subprocess.run(
            cmd, shell=True, text=True,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT
        )
        if p.returncode != 0:
            raise RuntimeError(f"Command failed ({p.returncode}):\n{p.stdout}")
        return p.stdout

    def _boolish(self, v):
        if isinstance(v, bool):
            return v
        if v is None:
            return False
        return str(v).strip().lower() in ('1', 'true', 't', 'yes', 'y', 'on')

    def _resolve_staging(self, staging_subpath):
        """
        Turn a Narrative staging selection into a local file path.
        If a real path is given (e.g., unit tests), pass through.
        """
        if not staging_subpath:
            return None
        if os.path.exists(staging_subpath):
            return os.path.abspath(staging_subpath)
        out = self.dfu.download_staging_file(
            {'staging_file_subdir_path': staging_subpath})
        return out['copy_file_path']

    def _feature_set_to_geneset_tsv(self, fs_ref, set_name_hint=None):
        """
        Load a KBaseCollections.FeatureSet and write TSV lines as:
            set_name<TAB>feature_id
        Returns the TSV file path.
        """
        objs = self.dfu.get_objects2({'objects': [{'ref': fs_ref}]})['data']
        if not objs:
            raise ValueError(f"FeatureSet not found: {fs_ref}")
        obj = objs[0]
        data = obj['data']
        info = obj['info']  # [obj_id, name, type, save_date, ver, saved_by, ws_id, ws_name, checksum, size, meta]
        fs_name = info[1]
        set_name = (set_name_hint or fs_name or "FeatureSet").strip()

        feats = set()
        elements = data.get('elements') or data.get('feature_ids') or {}
        if isinstance(elements, dict):
            for _, v in elements.items():
                if isinstance(v, dict):
                    if 'feature_id' in v and isinstance(v['feature_id'], str):
                        feats.add(v['feature_id'])
                    if 'feature_ids' in v and isinstance(v['feature_ids'], list):
                        feats.update([x for x in v['feature_ids'] if isinstance(x, str)])
                    if 'features' in v and isinstance(v['features'], list):
                        for f in v['features']:
                            if isinstance(f, dict):
                                fid = f.get('feature_id') or f.get('id')
                                if isinstance(fid, str):
                                    feats.add(fid)
                            elif isinstance(f, str):
                                feats.add(f)
                elif isinstance(v, list):
                    for f in v:
                        if isinstance(f, dict):
                            fid = f.get('feature_id') or f.get('id')
                            if isinstance(fid, str):
                                feats.add(fid)
                        elif isinstance(f, str):
                            feats.add(f)
        elif isinstance(elements, list):
            for f in elements:
                if isinstance(f, dict):
                    fid = f.get('feature_id') or f.get('id')
                    if isinstance(fid, str):
                        feats.add(fid)
                elif isinstance(f, str):
                    feats.add(f)

        if not feats:
            raise ValueError(f"No feature IDs found in FeatureSet {fs_ref}")

        out_path = os.path.join(self.scratch, f"geneset_{uuid.uuid4().hex}.tsv")
        with open(out_path, "w") as fh:
            for fid in sorted(feats):
                fh.write(f"{set_name}\t{fid}\n")
        return out_path

    def _mk_report(self, wsname, html_dir, attach_files, message="GRIN completed."):
        html_links = []
        file_links = []

        if html_dir and os.path.isdir(html_dir):
            zip_path = os.path.join(self.scratch, f"{uuid.uuid4()}.zip")
            self.dfu.pack_file({
                'file_path': html_dir,
                'pack': 'zip',
                'output_file_name': os.path.basename(zip_path)
            })
            sid = self.dfu.file_to_shock({'file_path': zip_path, 'make_handle': 0})['shock_id']
            html_links.append({'shock_id': sid, 'name': 'index.html', 'label': 'Open report'})

        for f in attach_files or []:
            if os.path.exists(f):
                sid = self.dfu.file_to_shock({'file_path': f, 'make_handle': 0})['shock_id']
                file_links.append({'shock_id': sid, 'name': os.path.basename(f), 'label': os.path.basename(f)})

        rep = self.kbr.create_extended_report({
            'workspace_name': wsname,
            'message': message,
            'direct_html_link_index': 0 if html_links else None,
            'html_links': html_links,
            'file_links': file_links
        })
        return {'report_name': rep['name'], 'report_ref': rep['ref']}
    #END_CLASS_METHODS

    def run_grin(self, ctx, params):
        """
        :param params: instance of type "RunGRINParams" -> structure includes:
           "workspace_name" (injected by Narrative), one of:
             - "feature_set_ref" (KBaseCollections.FeatureSet, preferred), or
             - "geneset_tsv_path" (legacy staging TSV),
           plus "multiplex_rdata_path", "restart", "tau_csv",
           "run_label", "verbosity", "plot", "simple_filenames", "output_name"
        :returns: ReportResults {report_name, report_ref}
        """
        #BEGIN run_grin
        ws = params.get('workspace_name')
        if not ws:
            raise ValueError("workspace_name is required")

        # Prefer FeatureSet → TSV conversion; else fall back to staging TSV
        geneset_tsv = None
        if params.get('feature_set_ref'):
            geneset_tsv = self._feature_set_to_geneset_tsv(
                params['feature_set_ref'],
                set_name_hint=params.get('run_label')
            )
        else:
            geneset_tsv = self._resolve_staging(params.get('geneset_tsv_path'))

        multiplex = self._resolve_staging(params.get('multiplex_rdata_path'))

        if not geneset_tsv or not os.path.exists(geneset_tsv):
            raise ValueError("Provide a FeatureSet (feature_set_ref) or a valid geneset_tsv_path.")
        if not multiplex or not os.path.exists(multiplex):
            raise ValueError("multiplex_rdata_path is required and must exist")

        # Output directory
        label = (params.get('output_name') or params.get('run_label') or 'GRIN').strip()
        safe_label = "".join(c if c.isalnum() or c in ('-', '_') else "_" for c in label)
        outdir = os.path.join(self.scratch, f"{safe_label}_{uuid.uuid4().hex}")
        os.makedirs(outdir, exist_ok=True)

        # Coerce and default flags
        restart = float(params.get('restart', 0.7))
        tau_csv = params.get('tau_csv', '1,1,1,1,1,1,1,1,1,1')
        run_label = params.get('run_label', 'run1')
        verbosity = int(params.get('verbosity', 0))
        plot_flag = '-p' if self._boolish(params.get('plot')) else ''
        simple_flag = '-s' if self._boolish(params.get('simple_filenames', 1)) else ''
        verbose_flag = '-v' if verbosity > 0 else ''

        # Build GRIN command
        cmd = (
            f"{RSCRIPT} {shlex.quote(GRIN_R)} "
            f"-d {shlex.quote(multiplex)} "
            f"-g {shlex.quote(geneset_tsv)} "
            f"-r {restart} "
            f"-t {shlex.quote(tau_csv)} "
            f"-m {shlex.quote(run_label)} "
            f"-o {shlex.quote(outdir)} "
            f"{plot_flag} {simple_flag} {verbose_flag}"
        )

        # Execute
        log = self._run_cmd(cmd)

        # Minimal HTML log
        html_dir = os.path.join(outdir, "html")
        os.makedirs(html_dir, exist_ok=True)
        with open(os.path.join(html_dir, "index.html"), "w") as fh:
            fh.write("<h2>GRIN finished</h2>\n")
            fh.write("<h3>Command</h3>\n")
            fh.write(f"<pre>{cmd}</pre>\n")
            fh.write("<h3>Log</h3>\n")
            fh.write(f"<pre>{log}</pre>\n")

        # Collect common GRIN outputs if present
        attachments = []
        for fname in ("retained_genes.txt", "removed_genes.txt",
                      "duplicates.txt", "not_in_multiplex.txt"):
            fpath = os.path.join(outdir, fname)
            if os.path.exists(fpath):
                attachments.append(fpath)

        result = self._mk_report(ws, html_dir, attachments,
                                 message=f"GRIN completed: {safe_label}")
        return [result]
        #END run_grin

    def status(self, ctx):
        #BEGIN_STATUS
        returnVal = {'state': "OK",
                     'message': "",
                     'version': self.VERSION,
                     'git_url': self.GIT_URL,
                     'git_commit_hash': self.GIT_COMMIT_HASH}
        #END_STATUS
        return [returnVal]
