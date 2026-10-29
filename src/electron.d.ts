export {};

declare global {
  interface Window {
    receiptPdf?: {
      saveOne: (payload: {fileName: string; html: string}) => Promise<{saved: boolean; filePath?: string}>;
      saveMany: (payload: {documents: {fileName: string; html: string}[]}) => Promise<{saved: boolean; directory?: string; count?: number}>;
    };
    rpaApi?: {
      call: (req: {method?: 'GET' | 'POST'; path: RpaApiPath; body?: unknown}) => Promise<{ok: boolean; status: number; data: any; error?: string}>;
    };
    rpa?: {
      exportClaims: (payload: RpaExportPayload) => Promise<{saved: boolean; reason?: string; root?: string; csvPath?: string; rows?: number; folders?: number; folderIssues?: number; folderCheck?: string; evidenceRoot?: string}>;
      launch: () => Promise<{ok: boolean; reason?: string; layout?: RpaLayoutInfo}>;
      layout: () => Promise<{ok: boolean; reason?: string; layout?: RpaLayoutInfo}>;
      onLayout: (callback: (info: RpaLayoutInfo) => void) => () => void;
      completed: () => Promise<{items: {course: string; round: string; company?: string}[]}>;
      openResults: () => Promise<{ok: boolean; dir: string; error?: string}>;
      openBackup: () => Promise<{ok: boolean; dir: string; error?: string}>;
    };
  }

  type RpaApiPath =
    | '/api/state' | '/api/run' | '/api/stop' | '/api/backups' | '/api/answer' | '/api/open'
    | '/api/companies' | '/api/macros' | '/api/macros/clone' | '/api/macros/promote' | '/api/macros/select';

  interface RpaLayoutInfo {
    mode: 'single' | 'dual';
    compact: boolean;
  }

  interface RpaExportPayload {
    rows: {course: string; round: string; start: string; end: string; company: string; bizNo?: string; headcount: number; amount: number; excludeReason?: string}[];
    receipts: {course: string; round: string; fileName: string; html: string}[];
  }
}
