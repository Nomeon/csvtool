import os
import threading
import queue
import traceback
from tkinter import filedialog
import ttkbootstrap as ttk
from ttkbootstrap.constants import *
import pandas as pd

# Import existing processing modules
import helpers
import partijen


class ProcessingThread(threading.Thread):
    """Thread for processing CSV files without blocking the UI."""

    def __init__(self, bucket_data, settings, message_queue):
        """Initialize the processing thread.

        Args:
            bucket_data (dict): {building_number: [file_paths]}
            settings (dict): All processing settings
            message_queue (queue.Queue): Queue for sending updates to UI
        """
        super().__init__(daemon=True)
        self.bucket_data = bucket_data
        self.settings = settings
        self.message_queue = message_queue

    def _send_message(self, msg_type, message, progress=None):
        """Send a message to the UI thread.

        Args:
            msg_type (str): Type of message ('status', 'error', 'progress', 'complete')
            message (str): The message text
            progress (int): Optional progress value (0-100)
        """
        print( f"[{msg_type.upper()}] {message}" )
        self.message_queue.put({
            'type': msg_type,
            'message': message,
            'progress': progress
        })

    def run(self):
        """Execute the CSV processing workflow."""
        try:
            # Load bulk and meterkast data
            self._send_message('status', 'Laden van configuratiebestanden...')

            bulkbb, bulkvh, bulkvmg = [], [], []
            meterkast = []
            prioriteit = pd.DataFrame()

            # Load priority CSV
            if self.settings['priority_path']:
                try:
                    prioriteit = pd.read_csv(self.settings['priority_path'])
                    self._send_message('status', 'Prioriteit CSV gevonden.')
                except FileNotFoundError:
                    self._send_message('status', 'Geen prioriteit CSV gevonden, standaard nesting wordt gebruikt.')

            # Load bulk CSV
            if self.settings['bulk_path']:
                try:
                    bulk = pd.read_csv(self.settings['bulk_path'])
                    self._send_message('status', 'Bulk CSV gevonden.')
                    bulkbb = bulk["BB"].tolist() if "BB" in bulk.columns else []
                    bulkvh = bulk["VH"].tolist() if "VH" in bulk.columns else []
                    bulkvmg = bulk["VMG"].tolist() if "VMG" in bulk.columns else []
                except FileNotFoundError:
                    self._send_message('status', 'Geen bulk CSV gevonden.')

            # Load meterkast CSV
            if self.settings['meterkast_path']:
                try:
                    meterkast_df = pd.read_csv(self.settings['meterkast_path'])
                    self._send_message('status', 'Meterkast CSV gevonden.')
                    meterkast = meterkast_df["Meterkast"].tolist() if "Meterkast" in meterkast_df.columns else []
                except FileNotFoundError:
                    self._send_message('status', 'Geen meterkast CSV gevonden.')

            # Process all CSV files from buckets
            self._send_message('status', 'Verwerken van CSV bestanden...')
            df_list = []
            total_files = sum(len(files) for files in self.bucket_data.values())
            processed_files = 0

            for building_number, file_paths in self.bucket_data.items():
                for file_path in file_paths:
                    try:
                        # Load and preprocess CSV
                        df = helpers.csv_to_df(file_path)

                        # Inject Projectnummer and Bouwnummer columns
                        df['Projectnummer'] = self.settings['project_number']
                        df['Bouwnummer'] = building_number

                        # Construct Modulenaam from GUI values and CSV Moduletype
                        df['Modulenaam'] = df.apply(
                            lambda row: f"{row['Projectnummer']}-{row['Bouwnummer']}-{row['Moduletype']}",
                            axis=1
                        )

                        df_list.append(df)

                        processed_files += 1
                        progress = int((processed_files / total_files) * 100)
                        self._send_message('progress', f'Verwerkt: {processed_files}/{total_files}', progress)

                    except Exception as e:
                        self._send_message('error', f'Fout bij verwerken van {os.path.basename(file_path)}: {str(e)}')

            # Combine all dataframes
            self._send_message('status', 'Combineren van dataframes...')
            df = helpers.combine_dfs(df_list=df_list)
            bns = df["Bouwnummer"].unique()
            prio = helpers.create_nesting(combined_df=df, prioriteit=prioriteit)

            # Get order numbers
            bborder = self.settings['order_bb'] if self.settings['order_bb'] else "IO-000000"
            vhorder = self.settings['order_vh'] if self.settings['order_vh'] else "IO-000000"
            vmgorder = self.settings['order_vmg'] if self.settings['order_vmg'] else "IO-000000"

            output_path = self.settings['output_path']

            # Generate VH Meterkast CSV (if enabled and meterkast data available)
            if self.settings['generate_vh'] and meterkast:
                try:
                    print(f"[DEBUG] Calling VH Meterkast")
                    self._send_message('status', 'Genereren VH Meterkast CSV...')
                    partijen.VH(df=df, ordernummer=vhorder, path=output_path, prio_dict=prio,
                              bulk_file=bulkvh, meterkast_file=meterkast, bulk=False, meterkast=True)
                except Exception as e:
                    error_msg = f"VH Meterkast failed: {type(e).__name__}: {str(e)}\n{traceback.format_exc()}"
                    self._send_message('error', error_msg)
                    print(error_msg)

            # Generate BULK files (across all buildings)
            if self.settings['generate_bb'] and bulkbb:
                try:
                    print(f"[DEBUG] Calling BB BULK")
                    self._send_message('status', 'Genereren BB BULK CSV...')
                    partijen.BB(df=df, ordernummer=bborder, path=output_path, prio_dict=prio,
                              bulk_file=bulkbb, bulk=True)
                except Exception as e:
                    error_msg = f"BB BULK failed: {type(e).__name__}: {str(e)}\n{traceback.format_exc()}"
                    self._send_message('error', error_msg)
                    print(error_msg)

            if self.settings['generate_vh'] and bulkvh:
                try:
                    print(f"[DEBUG] Calling VH BULK")
                    self._send_message('status', 'Genereren VH BULK CSV...')
                    partijen.VH(df=df, ordernummer=vhorder, path=output_path, prio_dict=prio,
                              bulk_file=bulkvh, meterkast_file=meterkast, bulk=True)
                except Exception as e:
                    error_msg = f"VH BULK failed: {type(e).__name__}: {str(e)}\n{traceback.format_exc()}"
                    self._send_message('error', error_msg)
                    print(error_msg)

            if self.settings['generate_vmg'] and bulkvmg:
                try:
                    print(f"[DEBUG] Calling VMG BULK")
                    self._send_message('status', 'Genereren VMG BULK CSV...')
                    partijen.VMG(df=df, ordernummer=vmgorder, path=output_path, prio_dict=prio,
                               bulk_file=bulkvmg, bulk=True)
                except Exception as e:
                    error_msg = f"VMG BULK failed: {type(e).__name__}: {str(e)}\n{traceback.format_exc()}"
                    self._send_message('error', error_msg)
                    print(error_msg)

            # Generate Houtlijst for all buildings combined
            if self.settings['generate_houtlijst']:
                try:
                    print(f"[DEBUG] Calling Houtlijst")
                    self._send_message('status', 'Genereren Houtlijst...')
                    partijen.Houtlijst(df=df, path=output_path)
                except Exception as e:
                    error_msg = f"Houtlijst failed: {type(e).__name__}: {str(e)}\n{traceback.format_exc()}"
                    self._send_message('error', error_msg)
                    print(error_msg)

            # Generate per-building outputs
            for idx, bn in enumerate(bns):
                self._send_message('status', f'Verwerken bouwnummer {bn} ({idx+1}/{len(bns)})...')
                df_bn = df[df["Bouwnummer"] == bn]

                if self.settings['generate_erp']:
                    try:
                        print(f"[DEBUG] Calling ERP for {bn}")
                        partijen.ERP(df=df_bn, path=output_path)
                    except Exception as e:
                        error_msg = f"ERP failed for {bn}: {type(e).__name__}: {str(e)}\n{traceback.format_exc()}"
                        self._send_message('error', error_msg)
                        print(error_msg)

                if self.settings['generate_ws198']:
                    try:
                        print(f"[DEBUG] Calling WS198 for {bn}")
                        partijen.WS198(df=df_bn, path=output_path)
                    except Exception as e:
                        error_msg = f"WS198 failed for {bn}: {type(e).__name__}: {str(e)}\n{traceback.format_exc()}"
                        self._send_message('error', error_msg)
                        print(error_msg)

                if self.settings['generate_bb']:
                    try:
                        print(f"[DEBUG] Calling BB for {bn}")
                        partijen.BB(df=df_bn, ordernummer=bborder, path=output_path, prio_dict=prio,
                                  bulk_file=bulkbb, bulk=False)
                    except Exception as e:
                        error_msg = f"BB failed for {bn}: {type(e).__name__}: {str(e)}\n{traceback.format_exc()}"
                        self._send_message('error', error_msg)
                        print(error_msg)

                if self.settings['generate_vh']:
                    try:
                        print(f"[DEBUG] Calling VH for {bn}")
                        partijen.VH(df=df_bn, ordernummer=vhorder, path=output_path, prio_dict=prio,
                                  bulk_file=bulkvh, meterkast_file=meterkast, bulk=False)
                    except Exception as e:
                        error_msg = f"VH failed for {bn}: {type(e).__name__}: {str(e)}\n{traceback.format_exc()}"
                        self._send_message('error', error_msg)
                        print(error_msg)

                if self.settings['generate_vmg']:
                    try:
                        print(f"[DEBUG] Calling VMG for {bn}")
                        partijen.VMG(df=df_bn, ordernummer=vmgorder, path=output_path, prio_dict=prio,
                                   bulk_file=bulkvmg, bulk=False)
                    except Exception as e:
                        error_msg = f"VMG failed for {bn}: {type(e).__name__}: {str(e)}\n{traceback.format_exc()}"
                        self._send_message('error', error_msg)
                        print(error_msg)

            self._send_message('complete', 'Alle CSV bestanden zijn succesvol verwerkt!', 100)

        except Exception as e:
            error_details = (
                f"Kritieke fout tijdens verwerking:\n"
                f"Error Type: {type(e).__name__}\n"
                f"Error Message: {str(e)}\n"
                f"\nFull Traceback:\n{traceback.format_exc()}"
            )
            self._send_message('error', error_details)
            print(error_details)  # Also print to console for debugging


class CSVMappingRow(ttk.Frame):
    """Custom widget representing a single CSV file with its bouwnummer assignments."""

    def __init__(self, parent, file_path, on_remove_callback, on_bouwnummers_change_callback):
        super().__init__(parent, borderwidth=1, relief="solid")
        self.file_path = file_path
        self.on_remove_callback = on_remove_callback
        self.on_bouwnummers_change_callback = on_bouwnummers_change_callback

        self.setup_ui()

    def setup_ui(self):
        """Setup the CSV mapping row UI."""
        self.config(padding=8)

        # Main grid layout: Filename | Bouwnummer Entry | Parsed Display | Remove Button
        self.columnconfigure(0, weight=2)  # Filename
        self.columnconfigure(1, weight=2)  # Entry field
        self.columnconfigure(2, weight=2)  # Parsed display
        self.columnconfigure(3, weight=0)  # Remove button

        # Filename label
        filename = os.path.basename(self.file_path)
        self.filename_label = ttk.Label(self, text=filename, font=("Segoe UI", 9), anchor=W)
        self.filename_label.grid(row=0, column=0, sticky=W+E, padx=(5, 10))

        # Bouwnummers entry
        self.bouwnummers_entry = ttk.Entry(self, font=("Segoe UI", 9))
        self.bouwnummers_entry.grid(row=0, column=1, sticky=W+E, padx=(0, 10))
        self.bouwnummers_entry.bind("<KeyRelease>", self._on_entry_change)
        self.bouwnummers_entry.bind("<FocusOut>", self._on_entry_change)

        # Parsed bouwnummers display (badge style)
        self.parsed_label = ttk.Label(
            self,
            text="",
            font=("Segoe UI", 9),
            foreground="#666",
            anchor=W
        )
        self.parsed_label.grid(row=0, column=2, sticky=W+E, padx=(0, 10))

        # Remove button
        remove_btn = ttk.Button(
            self,
            text="X",
            bootstyle="danger-outline",
            command=self._on_remove,
            width=5
        )
        remove_btn.grid(row=0, column=3, padx=(0, 5))

    def get_bouwnummers(self):
        """Parse and return list of bouwnummers from the entry field.

        Returns:
            list: List of trimmed, non-empty bouwnummers
        """
        raw_text = self.bouwnummers_entry.get()
        # Split by comma, trim whitespace, filter empty strings
        bouwnummers = [bn.strip() for bn in raw_text.split(',') if bn.strip()]
        return bouwnummers

    def has_bouwnummers(self):
        """Check if at least one bouwnummer is assigned."""
        return len(self.get_bouwnummers()) > 0

    def _on_entry_change(self, event=None):
        """Handle changes to the bouwnummers entry field."""
        bouwnummers = self.get_bouwnummers()

        # Update parsed display
        if bouwnummers:
            display_text = f"→ {len(bouwnummers)} BNs: {', '.join(bouwnummers[:3])}"
            if len(bouwnummers) > 3:
                display_text += f" (+{len(bouwnummers) - 3} meer)"
            self.parsed_label.config(text=display_text, foreground="#2c5aa0")
        else:
            self.parsed_label.config(text="⚠ Geen bouwnummers ingevoerd", foreground="#d9534f")

        # Notify parent of change
        if self.on_bouwnummers_change_callback:
            self.on_bouwnummers_change_callback()

    def _on_remove(self):
        """Handle row removal."""
        if self.on_remove_callback:
            self.on_remove_callback(self.file_path)


class CSVConverterApp(ttk.Window):
    """Main application window for CSV converter with CSV-to-bouwnummer mapping."""

    def __init__(self):
        super().__init__(themename="cosmo")

        self.title("CSV Converter 1.0.3")

        # Set window icon
        try:
            icon_path = helpers.resource_path("assets/gewoonhout.ico")
            self.iconbitmap(icon_path)
        except Exception as e:
            print(f"Warning: Could not load icon: {e}")

        # Data storage - NEW structure
        self.csv_mappings = {}  # file_path -> CSVMappingRow widget
        self.mapping_rows = []  # Ordered list of CSVMappingRow widgets for display

        # Threading and queue for processing
        self.message_queue = queue.Queue()
        self.processing_thread = None
        self.is_processing = False

        self.setup_ui()

        # Start monitoring queue for messages from processing thread
        self._check_message_queue()

        # Let tkinter calculate optimal size, then set minimum width only
        self.update_idletasks()
        width = self.winfo_reqwidth()

        # Set minimum width (at least 1200px for breathing room), but let height be dynamic
        min_width = max(1200, width)
        self.minsize(min_width, 0)

    def setup_ui(self):
        """Setup the main application UI."""
        # Main container
        main_container = ttk.Frame(self, padding=15)
        main_container.pack(fill=BOTH, expand=YES)

        # Top row - CSV Mapping (left) and Settings (right) side by side
        top_row = ttk.Frame(main_container)
        top_row.pack(fill=BOTH, expand=YES, pady=(0, 10))

        # CSV Mapping Section (left side)
        self._create_csv_mapping_section(top_row)

        # Settings Section (right side)
        self._create_settings_section(top_row)

        # Separator
        ttk.Separator(main_container, orient=HORIZONTAL).pack(fill=X, pady=10)

        # Action Section (full width)
        self._create_action_section(main_container)

    # ============================================================================
    # DATA ACCESS METHODS - Get configuration for processing
    # ============================================================================

    def get_bucket_data(self):
        """Get all CSV mapping data for processing.

        Returns:
            dict: {building_number: [file_paths]}
                  Note: This returns the INVERTED structure for compatibility with ProcessingThread.
                  Each file can have multiple bouwnummers, so the file will appear under each.
        """
        bucket_data = {}
        for file_path, mapping_row in self.csv_mappings.items():
            bouwnummers = mapping_row.get_bouwnummers()
            for bn in bouwnummers:
                if bn not in bucket_data:
                    bucket_data[bn] = []
                bucket_data[bn].append(file_path)
        return bucket_data

    def get_settings(self):
        """Get all processing settings.

        Returns:
            dict: All settings needed for processing
        """
        return {
            'project_number': self.project_number_entry.get(),
            'bulk_path': self.bulk_path_entry.get(),
            'meterkast_path': self.meterkast_path_entry.get(),
            'priority_path': self.priority_path_entry.get(),
            'output_path': self.output_path_entry.get(),
            'order_bb': self.bb_order_entry.get(),
            'order_vh': self.vh_order_entry.get(),
            'order_vmg': self.vmg_order_entry.get(),
            'generate_erp': self.erp_var.get(),
            'generate_vh': self.vh_var.get(),
            'generate_bb': self.bb_var.get(),
            'generate_vmg': self.vmg_var.get(),
            'generate_ws198': self.ws198_var.get(),
            'generate_houtlijst': self.houtlijst_var.get(),
        }

    def validate_configuration(self):
        """Validate all settings before processing.

        Returns:
            tuple: (is_valid: bool, error_message: str)
        """
        # Check if any CSVs exist
        if not self.csv_mappings:
            return False, "Geen CSV bestanden geselecteerd!"

        # Check that all CSVs have at least one bouwnummer
        for file_path, mapping_row in self.csv_mappings.items():
            if not mapping_row.has_bouwnummers():
                filename = os.path.basename(file_path)
                return False, f"'{filename}' heeft geen bouwnummers toegewezen!"

        return True, ""

    # ============================================================================
    # UI CREATION METHODS
    # ============================================================================

    def _create_csv_mapping_section(self, parent):
        """Create the CSV mapping section."""
        section_frame = ttk.LabelFrame(parent, text="CSV BESTANDEN & BOUWNUMMERS", padding=15, bootstyle="primary")
        section_frame.pack(side=LEFT, fill=BOTH, expand=YES, padx=(0, 10))

        # Warning label
        warning_label = ttk.Label(
            section_frame,
            text="Let op! Vul bloknummer + bouwnummer in, dus b.v. A1-01, A1-02.",
            font=("Segoe UI", 9),
            foreground="#d9534f"
        )
        warning_label.pack(anchor=W, pady=(0, 5))

        # Top row: Add CSV button and summary
        top_row = ttk.Frame(section_frame)
        top_row.pack(fill=X, pady=(0, 10))

        add_csv_btn = ttk.Button(
            top_row,
            text="+ CSV Toevoegen",
            bootstyle="success",
            command=self._on_add_csv_files,
            width=20
        )
        add_csv_btn.pack(side=LEFT, padx=(0, 10))

        self.summary_label = ttk.Label(
            top_row,
            text="0 CSVs → 0 bouwnummers",
            font=("Segoe UI", 10, "bold"),
            foreground="#2c5aa0"
        )
        self.summary_label.pack(side=LEFT)

        # Table header
        header_frame = ttk.Frame(section_frame)
        header_frame.pack(fill=X, pady=(5, 2))

        header_frame.columnconfigure(0, weight=2)
        header_frame.columnconfigure(1, weight=2)
        header_frame.columnconfigure(2, weight=2)
        header_frame.columnconfigure(3, weight=0)

        ttk.Label(header_frame, text="Bestandsnaam", font=("Segoe UI", 9, "bold")).grid(row=0, column=0, sticky=W, padx=(5, 10))
        ttk.Label(header_frame, text="Bouwnummers (gescheiden door komma)", font=("Segoe UI", 9, "bold")).grid(row=0, column=1, sticky=W, padx=(0, 10))
        ttk.Label(header_frame, text="Controle", font=("Segoe UI", 9, "bold")).grid(row=0, column=2, sticky=W, padx=(0, 10))
        ttk.Label(header_frame, text="", font=("Segoe UI", 9, "bold")).grid(row=0, column=3)

        # Separator after header
        ttk.Separator(section_frame, orient=HORIZONTAL).pack(fill=X, pady=(2, 5))

        # Scrollable frame for CSV mapping rows
        scroll_container = ttk.Frame(section_frame)
        scroll_container.pack(fill=BOTH, expand=YES)

        # Vertical scrollbar
        v_scrollbar = ttk.Scrollbar(scroll_container, orient=VERTICAL)
        v_scrollbar.pack(side=RIGHT, fill=Y)

        # Canvas for scrolling
        self.mappings_canvas = ttk.Canvas(scroll_container, yscrollcommand=v_scrollbar.set, height=300)
        self.mappings_canvas.pack(side=LEFT, fill=BOTH, expand=YES)
        v_scrollbar.config(command=self.mappings_canvas.yview)

        # Inner frame to hold mapping rows
        self.mappings_container = ttk.Frame(self.mappings_canvas)
        self.canvas_window = self.mappings_canvas.create_window((0, 0), window=self.mappings_container, anchor=NW)

        # Bind to configure events to update scroll region
        self.mappings_container.bind("<Configure>", self._on_mappings_configure)
        self.mappings_canvas.bind("<Configure>", self._on_canvas_configure)

    def _create_settings_section(self, parent):
        """Create the settings section."""
        section_frame = ttk.LabelFrame(parent, text="INSTELLINGEN", padding=15, bootstyle="secondary")
        section_frame.pack(side=LEFT, fill=BOTH, expand=YES)

        # File pickers grid
        files_frame = ttk.Frame(section_frame)
        files_frame.pack(fill=X, pady=(0, 15))

        # Bulk CSV
        self._create_file_picker(files_frame, "Bulk CSV:")
        self.bulk_path_entry = self.last_entry

        # Meterkast CSV
        self._create_file_picker(files_frame, "Meterkast CSV:")
        self.meterkast_path_entry = self.last_entry

        # Priority CSV
        self._create_file_picker(files_frame, "Prioriteit CSV:")
        self.priority_path_entry = self.last_entry

        # Output folder
        self._create_folder_picker(files_frame, "Output map:")
        self.output_path_entry = self.last_entry

        # Project number and Order numbers
        order_frame = ttk.Frame(section_frame)
        order_frame.pack(fill=X, pady=(0, 10))

        # Project number
        ttk.Label(order_frame, text="Projectnummer:", font=("Segoe UI", 10, "bold")).pack(anchor=W, pady=(0, 5))

        project_row = ttk.Frame(order_frame)
        project_row.pack(fill=X, pady=(0, 10))

        ttk.Label(project_row, text="Project:").pack(side=LEFT, padx=(0, 5))
        self.project_number_entry = ttk.Entry(project_row, width=20)
        self.project_number_entry.pack(side=LEFT)

        # Order numbers
        ttk.Label(order_frame, text="Ordernummers:", font=("Segoe UI", 10, "bold")).pack(anchor=W, pady=(0, 5))

        order_inputs = ttk.Frame(order_frame)
        order_inputs.pack(fill=X)

        ttk.Label(order_inputs, text="BB:").pack(side=LEFT, padx=(0, 5))
        self.bb_order_entry = ttk.Entry(order_inputs, width=12)
        self.bb_order_entry.pack(side=LEFT, padx=(0, 15))

        ttk.Label(order_inputs, text="VH:").pack(side=LEFT, padx=(0, 5))
        self.vh_order_entry = ttk.Entry(order_inputs, width=12)
        self.vh_order_entry.pack(side=LEFT, padx=(0, 15))

        ttk.Label(order_inputs, text="VMG:").pack(side=LEFT, padx=(0, 5))
        self.vmg_order_entry = ttk.Entry(order_inputs, width=12)
        self.vmg_order_entry.pack(side=LEFT)

        # Checkboxes in grid layout
        checkbox_frame = ttk.Frame(section_frame)
        checkbox_frame.pack(fill=X)

        ttk.Label(checkbox_frame, text="Genereer:", font=("Segoe UI", 10, "bold")).grid(row=0, column=0, columnspan=3, sticky=W, pady=(0, 8))

        # Row 1
        self.vh_var = ttk.BooleanVar(value=True)
        ttk.Checkbutton(checkbox_frame, text="Van Hulst", variable=self.vh_var, bootstyle="primary-round-toggle").grid(row=1, column=0, sticky=W, padx=(0, 30), pady=3)

        self.erp_var = ttk.BooleanVar(value=True)
        ttk.Checkbutton(checkbox_frame, text="ERP", variable=self.erp_var, bootstyle="primary-round-toggle").grid(row=1, column=1, sticky=W, padx=(0, 30), pady=3)

        self.vmg_var = ttk.BooleanVar(value=True)
        ttk.Checkbutton(checkbox_frame, text="VMG", variable=self.vmg_var, bootstyle="primary-round-toggle").grid(row=1, column=2, sticky=W, pady=3)

        # Row 2
        self.bb_var = ttk.BooleanVar(value=True)
        ttk.Checkbutton(checkbox_frame, text="Boerboom", variable=self.bb_var, bootstyle="primary-round-toggle").grid(row=2, column=0, sticky=W, padx=(0, 30), pady=3)

        self.ws198_var = ttk.BooleanVar(value=False)
        ttk.Checkbutton(checkbox_frame, text="WS198", variable=self.ws198_var, bootstyle="primary-round-toggle").grid(row=2, column=1, sticky=W, padx=(0, 30), pady=3)

        self.houtlijst_var = ttk.BooleanVar(value=False)
        ttk.Checkbutton(checkbox_frame, text="Houtlijst", variable=self.houtlijst_var, bootstyle="primary-round-toggle").grid(row=2, column=2, sticky=W, pady=3)

    def _create_file_picker(self, parent, label_text):
        """Create a file picker row."""
        row_frame = ttk.Frame(parent)
        row_frame.pack(fill=X, pady=2)

        ttk.Label(row_frame, text=label_text, width=15, anchor=W).pack(side=LEFT, padx=(0, 5))

        entry = ttk.Entry(row_frame)
        entry.pack(side=LEFT, fill=X, expand=YES, padx=(0, 5))

        browse_btn = ttk.Button(
            row_frame,
            text="Bladeren",
            bootstyle="secondary-outline",
            command=lambda e=entry: self._browse_file(e),
            width=10
        )
        browse_btn.pack(side=RIGHT)

        self.last_entry = entry

    def _create_folder_picker(self, parent, label_text):
        """Create a folder picker row."""
        row_frame = ttk.Frame(parent)
        row_frame.pack(fill=X, pady=2)

        ttk.Label(row_frame, text=label_text, width=15, anchor=W).pack(side=LEFT, padx=(0, 5))

        entry = ttk.Entry(row_frame)
        entry.pack(side=LEFT, fill=X, expand=YES, padx=(0, 5))

        browse_btn = ttk.Button(
            row_frame,
            text="Bladeren",
            bootstyle="secondary-outline",
            command=lambda e=entry: self._browse_folder(e),
            width=10
        )
        browse_btn.pack(side=RIGHT)

        self.last_entry = entry

    def _create_action_section(self, parent):
        """Create the action section with process button, progress bar, and status."""
        section_frame = ttk.Frame(parent, padding=10)
        section_frame.pack(fill=X)

        # Button container for process and reset buttons side by side
        button_container = ttk.Frame(section_frame)
        button_container.pack(pady=(0, 10))

        # Process button (starts disabled)
        self.process_btn = ttk.Button(
            button_container,
            text="Verwerk alle bestanden",
            bootstyle="success",
            command=self._on_process,
            width=30,
            state='disabled'
        )
        self.process_btn.pack(side=LEFT, padx=(0, 10))

        # Reset button
        self.reset_btn = ttk.Button(
            button_container,
            text="Reset",
            bootstyle="secondary-outline",
            command=self._on_reset,
            width=15
        )
        self.reset_btn.pack(side=LEFT)

        # Progress bar
        self.progress_bar = ttk.Progressbar(
            section_frame,
            bootstyle="success-striped",
            mode="determinate",
            maximum=100,
            value=0
        )
        self.progress_bar.pack(fill=X, pady=(0, 10))

        # Status label
        self.status_label = ttk.Label(
            section_frame,
            text="Status: Gereed",
            font=("Segoe UI", 10),
            anchor=CENTER
        )
        self.status_label.pack()

    # ============================================================================
    # EVENT HANDLERS - UI Interactions
    # ============================================================================

    def _on_add_csv_files(self):
        """Handle adding CSV files."""
        files = filedialog.askopenfilenames(
            title="Selecteer CSV bestanden",
            filetypes=[("CSV files", "*.csv"), ("All files", "*.*")]
        )

        if files:
            added_count = 0
            for file_path in files:
                # Prevent duplicate files
                if file_path not in self.csv_mappings:
                    self._add_mapping_row(file_path)
                    added_count += 1

            if added_count > 0:
                self._update_summary()
                self._update_status(f"{added_count} bestand(en) toegevoegd")
            else:
                self._update_status("Alle geselecteerde bestanden zijn al toegevoegd", error=True)

    def _on_remove_csv(self, file_path):
        """Handle CSV row removal."""
        if file_path in self.csv_mappings:
            # Remove and destroy widget
            mapping_row = self.csv_mappings[file_path]
            mapping_row.destroy()
            del self.csv_mappings[file_path]
            self.mapping_rows.remove(mapping_row)

            self._update_summary()
            self._validate_and_update_button()
            self._update_status(f"Bestand verwijderd")

    def _on_bouwnummers_change(self):
        """Handle changes to any bouwnummer field."""
        self._update_summary()
        self._validate_and_update_button()

    def _on_process(self):
        """Handle process button click - entry point for processing."""
        # Prevent multiple simultaneous processing threads
        if self.is_processing:
            self._update_status("Er wordt al verwerkt...", error=True)
            return

        # Validate configuration
        is_valid, error_msg = self.validate_configuration()
        if not is_valid:
            self._update_status(f"{error_msg}", error=True)
            return

        # Get data for processing
        bucket_data = self.get_bucket_data()
        settings = self.get_settings()

        # Reset progress bar
        self.progress_bar['value'] = 0

        # Disable process button during processing
        self.process_btn.config(state='disabled')
        self.is_processing = True

        # Start processing in background thread
        self._start_processing(bucket_data, settings)
        self._update_status("Verwerking gestart...")

    def _on_reset(self):
        """Handle reset button click - clear all state and reset UI."""
        # Don't allow reset during processing
        if self.is_processing:
            self._update_status("Kan niet resetten tijdens verwerking...", error=True)
            return

        # Clear all CSV mappings
        for file_path in list(self.csv_mappings.keys()):
            mapping_row = self.csv_mappings[file_path]
            mapping_row.destroy()
            del self.csv_mappings[file_path]

        self.mapping_rows.clear()

        # Reset progress bar
        self.progress_bar['value'] = 0

        # Reset status label
        self.status_label.config(text="Status: Gereed", foreground="#000000")

        # Reset processing flag
        self.is_processing = False

        # Update summary and button state
        self._update_summary()
        self._validate_and_update_button()

        self._update_status("Tool gereset - klaar voor nieuwe verwerking")

    def _browse_file(self, entry_widget):
        """Browse for a file."""
        filename = filedialog.askopenfilename(
            title="Selecteer bestand",
            filetypes=[("CSV-bestanden", "*.csv"), ("Alle bestanden", "*.*")]
        )
        if filename:
            entry_widget.delete(0, END)
            entry_widget.insert(0, filename)

    def _browse_folder(self, entry_widget):
        """Browse for a folder."""
        folder = filedialog.askdirectory(title="Selecteer output map")
        if folder:
            entry_widget.delete(0, END)
            entry_widget.insert(0, folder)

    # ============================================================================
    # PROCESSING METHODS - Integration with business logic
    # ============================================================================

    def _start_processing(self, bucket_data, settings):
        """Start the CSV processing workflow in a background thread.

        Args:
            bucket_data (dict): {building_number: [file_paths]}
            settings (dict): All processing settings
        """
        # Create and start processing thread
        self.processing_thread = ProcessingThread(bucket_data, settings, self.message_queue)
        self.processing_thread.start()

    def _check_message_queue(self):
        """Check for messages from the processing thread and update UI accordingly.

        This method runs periodically via tkinter's after() method to check for messages
        from the background processing thread and update the UI in a thread-safe manner.
        """
        try:
            # Check if there are messages in the queue (non-blocking)
            while not self.message_queue.empty():
                message = self.message_queue.get_nowait()
                msg_type = message['type']
                msg_text = message['message']
                progress = message.get('progress')

                if msg_type == 'status':
                    self._update_status(msg_text)
                    if progress is not None:
                        self.progress_bar['value'] = progress

                elif msg_type == 'progress':
                    self._update_status(msg_text)
                    if progress is not None:
                        self.progress_bar['value'] = progress

                elif msg_type == 'error':
                    self._update_status(msg_text, error=True)

                elif msg_type == 'complete':
                    self._update_status(msg_text)
                    self.progress_bar['value'] = 100
                    self.process_btn.config(state='normal')
                    self.is_processing = False

        except queue.Empty:
            pass

        # Schedule the next check (every 100ms)
        self.after(100, self._check_message_queue)

    # ============================================================================
    # UTILITY METHODS - Internal helpers
    # ============================================================================

    def _add_mapping_row(self, file_path):
        """Create and add a new CSV mapping row."""
        mapping_row = CSVMappingRow(
            self.mappings_container,
            file_path,
            self._on_remove_csv,
            self._on_bouwnummers_change
        )
        mapping_row.pack(fill=X, pady=2)

        self.csv_mappings[file_path] = mapping_row
        self.mapping_rows.append(mapping_row)

    def _on_mappings_configure(self, event=None):
        """Update canvas scroll region when mappings container changes."""
        self.mappings_canvas.configure(scrollregion=self.mappings_canvas.bbox("all"))

    def _on_canvas_configure(self, event):
        """Update the inner frame width when canvas is resized."""
        canvas_width = event.width
        self.mappings_canvas.itemconfig(self.canvas_window, width=canvas_width)

    def _update_summary(self):
        """Update the summary label showing CSV count and total bouwnummers."""
        csv_count = len(self.csv_mappings)
        total_bouwnummers = sum(len(row.get_bouwnummers()) for row in self.csv_mappings.values())

        self.summary_label.config(text=f"{csv_count} CSVs → {total_bouwnummers} bouwnummers")

    def _validate_and_update_button(self):
        """Validate configuration and enable/disable process button accordingly."""
        is_valid, _ = self.validate_configuration()

        if is_valid:
            self.process_btn.config(state='normal')
        else:
            self.process_btn.config(state='disabled')

    def _update_status(self, message, error=False):
        """Update the status label."""
        prefix = "Status: "
        if error:
            prefix = "Error: "
        self.status_label.config(text=f"{prefix}{message}")


if __name__ == "__main__":
    app = CSVConverterApp()
    app.mainloop()
