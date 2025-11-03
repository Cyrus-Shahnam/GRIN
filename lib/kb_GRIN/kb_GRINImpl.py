# -*- coding: utf-8 -*-
#BEGIN_HEADER
import os
import uuid
import shlex
import subprocess

from installed_clients.DataFileUtilClient import DataFileUtil
from installed_clients.KBaseReportClient import KBaseReport

# Absolute paths inside the micromamba env you created in the Dockerfile
RSCRIPT = "/usr/local/bin/micromamba run -n grin Rscript"
GRIN_R  = "/opt/GRIN/R/GRIN.R"
#END_HEADER


class kb_GRIN:
    '''
    Module Name:
    kb_GRIN

    Module Description:
    Wraps the GRIN R CLI with micromamba-managed dependencies.
    '''

    #BEGIN_CLASS_HEADER
    # You can place class-level constants or helpers here; this section is preserved on recompile.
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
    def _resolve_input_path(self, maybe_staging_path):
        """
        Resolve a Narrative "staging" selection to a local file path.
        If a real path was provided (e.g., unit tests), return as-is.
        """
        if not maybe_staging_path:
            return None
        if os.path.exists(maybe_staging_path):
            return os.path.abspath(maybe_staging_path)
        out = self.dfu.download_staging_file(
            {'staging_file_subdir_path': maybe_staging_path})
        return out['copy_file_path']

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
        """
        Convert Narrative checkbox/text inputs to bool.
        Accepts 1/0, '1'/'0', 'true'/'false', True/False, yes/no, on/off.
        """
        if isinstance(v, bool):
            return v
        if v is None:
            return False
        s = str(v).strip().lower()
        return s in ('1', 'true', 't', 'yes', 'y', 'on')

    def _mk_report(self, wsname, html_dir, attach_files, message="GRIN completed."):
        html_links = []
        file_links = []

        # Package HTML dir (if present) into a zip, expose index.html
        if html_dir and os.path.isdir(html_dir):
            zip_path = os.path.join(self.scratch, f"{uuid.uuid4()}.zip")
            self.dfu.pack_file({
                'file_path': html_dir,
                'pack': 'zip',
                'output_file_name': os.path.basename(zip_path)
            })
            sid = self.dfu.file_to_shock({'file_path': zip_path, 'make_handle': 0})['shock_id']
            html_links.append({'shock_id': sid, 'name': 'index.html', 'label': 'Open report'})

        # Attach artifacts if they exist
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
        :param params: dict with keys
            workspace_name, geneset_tsv_path, multiplex_rdata_path,
            restart, tau_csv, run_label, verbosity, plot, simple_filenames, output_name
        :returns: list with one dict: {report_name, report_ref}
        """
        #BEGIN run_grin
        ws = params.get('workspace_name')
        if not ws:
            raise ValueError("workspace_name is required")

        geneset = self._resolve_input_path(params.get('geneset_tsv_path'))
        multiplex = self._resolve_input_path(params.get('multiplex_rdata_path'))
        if not geneset or not os.path.exists(geneset):
            raise ValueError("geneset_tsv_path is required and must exist")
        if not multiplex or not os.path.exists(multiplex):
            raise ValueError("multiplex_rdata_path is required and must exist")

        # Output directory (optionally use output_name as a hint)
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

        # Build GRIN command (no --threads)
        cmd = (
            f"{RSCRIPT} {shlex.quote(GRIN_R)} "
            f"-d {shlex.quote(multiplex)} "
            f"-g {shlex.quote(geneset)} "
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
        for fname in (
            "retained_genes.txt",
            "removed_genes.txt",
            "duplicates.txt",
            "not_in_multiplex.txt"
        ):
            fpath = os.path.join(outdir, fname)
            if os.path.exists(fpath):
                attachments.append(fpath)

        result = self._mk_report(ws, html_dir, attachments, message=f"GRIN completed: {safe_label}")
        return [result]
        #END run_grin
