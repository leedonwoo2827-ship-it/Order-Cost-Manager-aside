export {};

declare global {
  interface Window {
    receiptPdf?: {
      saveOne: (payload: {fileName: string; html: string}) => Promise<{saved: boolean; filePath?: string}>;
      saveMany: (payload: {documents: {fileName: string; html: string}[]}) => Promise<{saved: boolean; directory?: string; count?: number}>;
    };
    rpaApi?: {
      call: (req: {method?: 'GET' | 'POST'; path: '/api/state' | '/api/run' | '/api/stop'; body?: unknown}) => Promise<{ok: boolean; status: number; data: any; error?: string}>;
    };
    rpa?: {
      exportClaims: (payload: RpaExportPayload) => Promise<{saved: boolean; reason?: string; root?: string; csvPath?: string; rows?: number; receipts?: number}>;
      launch: () => Promise<{ok: boolean; reason?: string}>;
      completed: () => Promise<{items: {course: string; round: string}[]}>;
      openResults: () => Promise<{ok: boolean; dir: string; error?: string}>;
      openBackup: () => Promise<{ok: boolean; dir: string; error?: string}>;
    };
  }

  interface RpaExportPayload {
    rows: {course: string; round: string; start: string; end: string; company: string; headcount: number; amount: number}[];
    receipts: {course: string; round: string; fileName: string; html: string}[];
  }
}
