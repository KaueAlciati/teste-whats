"use client";

import { useRef, useState } from "react";
import { AlertTriangle, CheckCircle2, FileText, Loader2, UploadCloud, X } from "lucide-react";
import {
  api,
  type ImportColumnMapping,
  type ImportConfirmRow,
  type ImportPreviewResponse,
  type ImportPreviewRow,
} from "@/lib/api";
import { useHandleFetchError } from "@/hooks/useHandleFetchError";
import { useToast } from "@/contexts/ToastContext";

type RowEdit = {
  included: boolean;
  description: string;
  category: string;
  type: "income" | "expense" | "";
};

type Props = {
  open: boolean;
  onClose: () => void;
  onImported: () => void | Promise<void>;
};

const EMPTY_MAPPING: ImportColumnMapping = {
  date_column: "",
  description_column: "",
  amount_column: null,
  type_column: null,
  credit_column: null,
  debit_column: null,
};

export function StatementImportDialog({ open, onClose, onImported }: Props) {
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [file, setFile] = useState<File | null>(null);
  const [preview, setPreview] = useState<ImportPreviewResponse | null>(null);
  const [mapping, setMapping] = useState<ImportColumnMapping>(EMPTY_MAPPING);
  const [edits, setEdits] = useState<Record<number, RowEdit>>({});
  const [analyzing, setAnalyzing] = useState(false);
  const [confirming, setConfirming] = useState(false);
  const [result, setResult] = useState<{ imported: number; skipped: number } | null>(null);
  const handleFetchError = useHandleFetchError();
  const { addToast } = useToast();

  if (!open) return null;

  function reset() {
    setFile(null);
    setPreview(null);
    setMapping(EMPTY_MAPPING);
    setEdits({});
    setResult(null);
    if (fileInputRef.current) fileInputRef.current.value = "";
  }

  function close() {
    if (analyzing || confirming) return;
    reset();
    onClose();
  }

  async function analyze(selectedFile: File, selectedMapping?: ImportColumnMapping) {
    if (!/\.(csv|pdf|jpe?g|png)$/i.test(selectedFile.name)) {
      addToast("error", "Selecione um arquivo CSV, PDF, JPG, JPEG ou PNG.");
      return;
    }
    setAnalyzing(true);
    setFile(selectedFile);
    setResult(null);
    try {
      const response = await api.previewImport(selectedFile, selectedMapping);
      setPreview(response);
      if (response.mapping) setMapping(response.mapping);
      if (!response.mapping_required) {
        setEdits(createInitialEdits(response.rows));
      }
    } catch (error) {
      await handleFetchError(error, "Erro ao analisar o extrato:");
    } finally {
      setAnalyzing(false);
    }
  }

  async function applyMapping() {
    if (!file) return;
    if (!mapping.date_column || !mapping.description_column) {
      addToast("error", "Mapeie as colunas de data e descrição.");
      return;
    }
    if (!mapping.amount_column && !mapping.credit_column && !mapping.debit_column) {
      addToast("error", "Mapeie valor ou ao menos crédito/débito.");
      return;
    }
    await analyze(file, mapping);
  }

  async function confirm() {
    if (!preview) return;
    const selectedRows = preview.rows.filter(
      (row) =>
        row.status !== "invalid" &&
        edits[row.id]?.included &&
        Boolean(edits[row.id]?.type || row.type),
    );
    const rows: ImportConfirmRow[] = selectedRows.map((row) => ({
      date: row.date || undefined,
      amount: row.amount ?? undefined,
      type: edits[row.id].type || row.type || undefined,
      description: edits[row.id].description.trim(),
      category: edits[row.id].category.trim() || undefined,
      allow_duplicate: row.status === "possible_duplicate",
    }));
    if (!rows.length) {
      addToast("error", "Selecione ao menos uma movimentação válida.");
      return;
    }

    setConfirming(true);
    try {
      const response = await api.confirmImport(rows, preview.source);
      setResult({
        imported: response.imported,
        skipped: response.skipped_duplicates ?? response.skipped ?? 0,
      });
      await onImported();
      addToast("success", "Extrato importado com sucesso.");
    } catch (error) {
      await handleFetchError(error, "Erro ao confirmar a importação:");
    } finally {
      setConfirming(false);
    }
  }

  const selectedCount = preview
    ? preview.rows.filter((row) => edits[row.id]?.included).length
    : 0;

  return (
    <div className="fixed inset-0 z-[70] flex items-center justify-center bg-black/70 p-4" role="dialog" aria-modal="true" aria-labelledby="import-title">
      <div className="flex max-h-[92vh] w-full max-w-5xl flex-col overflow-hidden rounded-2xl border border-zinc-800 bg-zinc-950 shadow-2xl">
        <header className="flex items-start justify-between gap-4 border-b border-zinc-800 p-5">
          <div>
            <h2 id="import-title" className="text-xl font-bold">Importar extrato</h2>
            <p className="mt-1 text-sm text-zinc-400">Analise e revise o extrato antes de salvar qualquer movimentação.</p>
          </div>
          <button onClick={close} disabled={analyzing || confirming} aria-label="Fechar importação" className="rounded-lg p-2 text-zinc-500 hover:bg-zinc-900 hover:text-zinc-200 disabled:opacity-40">
            <X size={20} />
          </button>
        </header>

        <div className="overflow-y-auto p-5">
          {!preview && !result && (
            <div className="rounded-2xl border-2 border-dashed border-zinc-800 p-10 text-center">
              {analyzing ? (
                <div className="flex flex-col items-center gap-3 text-zinc-400">
                  <Loader2 className="animate-spin" size={32} />
                  <p>Analisando o extrato...</p>
                </div>
              ) : (
                <>
                  <UploadCloud className="mx-auto mb-4 text-zinc-500" size={40} />
                  <p className="font-medium">Selecione o extrato baixado do seu banco</p>
                  <p className="mb-4 mt-1 text-sm text-zinc-500">CSV, PDF, JPG, JPEG ou PNG · até 10 MB</p>
                  <button onClick={() => fileInputRef.current?.click()} className="rounded-xl bg-emerald-500 px-5 py-2.5 font-semibold text-emerald-950 hover:bg-emerald-400">
                    Selecionar arquivo
                  </button>
                  <input ref={fileInputRef} type="file" accept=".csv,.pdf,.jpg,.jpeg,.png,text/csv,application/pdf,image/jpeg,image/png" className="hidden" onChange={(event) => {
                    const selected = event.target.files?.[0];
                    if (selected) void analyze(selected);
                  }} />
                </>
              )}
            </div>
          )}

          {preview?.mapping_required && !result && (
            <MappingForm
              columns={preview.columns ?? []}
              mapping={mapping}
              sampleRows={preview.sample_rows ?? []}
              analyzing={analyzing}
              onChange={setMapping}
              onApply={() => void applyMapping()}
              onCancel={reset}
            />
          )}

          {preview && !preview.mapping_required && !result && (
            <div className="space-y-4">
              <div className="flex items-center gap-3 rounded-xl border border-zinc-800 bg-zinc-900/50 p-4">
                <FileText className="shrink-0 text-zinc-500" size={20} />
                <div className="min-w-0">
                  <p className="truncate font-medium">{preview.filename}</p>
                  <p className="text-xs text-zinc-500">{preview.total} linhas · {preview.ready ?? 0} prontas · {preview.possible_duplicates ?? 0} possíveis duplicadas · {preview.needs_review ?? 0} para revisar · {preview.invalid ?? 0} inválidas</p>
                </div>
              </div>

              <div className="overflow-x-auto rounded-xl border border-zinc-800">
                <table className="w-full min-w-[820px] text-sm">
                  <thead className="bg-zinc-900 text-left text-zinc-500">
                    <tr>
                      <th className="p-3"><span className="sr-only">Selecionar</span></th>
                      <th className="p-3">Data</th>
                      <th className="p-3">Descrição</th>
                      <th className="p-3">Tipo</th>
                      <th className="p-3 text-right">Valor</th>
                      <th className="p-3">Categoria sugerida</th>
                      <th className="p-3">Status</th>
                    </tr>
                  </thead>
                  <tbody>
                    {preview.rows.map((row) => (
                      <PreviewTableRow key={row.id} row={row} edit={edits[row.id]} onChange={(change) => setEdits((current) => ({ ...current, [row.id]: { ...current[row.id], ...change } }))} />
                    ))}
                  </tbody>
                </table>
              </div>

              <div className="flex flex-col justify-between gap-3 rounded-xl border border-zinc-800 bg-zinc-900/50 p-4 sm:flex-row sm:items-center">
                <p className="text-sm text-zinc-400"><strong className="text-zinc-200">{selectedCount}</strong> movimentações selecionadas. Possíveis duplicadas só entram quando marcadas explicitamente.</p>
                <div className="flex gap-2">
                  <button onClick={reset} className="rounded-xl border border-zinc-700 px-4 py-2.5 text-sm text-zinc-300 hover:border-zinc-600">Cancelar</button>
                  <button onClick={() => void confirm()} disabled={confirming || selectedCount === 0} className="flex items-center gap-2 rounded-xl bg-emerald-500 px-5 py-2.5 font-semibold text-emerald-950 hover:bg-emerald-400 disabled:opacity-50">
                    {confirming && <Loader2 className="animate-spin" size={16} />}
                    Confirmar importação
                  </button>
                </div>
              </div>
            </div>
          )}

          {result && (
            <div className="py-10 text-center">
              <CheckCircle2 className="mx-auto text-emerald-400" size={44} />
              <h3 className="mt-4 text-xl font-bold">Importação concluída</h3>
              <p className="mt-2 text-zinc-400">{result.imported} movimentações importadas{result.skipped ? ` e ${result.skipped} duplicadas ignoradas` : ""}.</p>
              <button onClick={close} className="mt-6 rounded-xl bg-emerald-500 px-5 py-2.5 font-semibold text-emerald-950 hover:bg-emerald-400">Voltar ao extrato</button>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

function MappingForm({ columns, mapping, sampleRows, analyzing, onChange, onApply, onCancel }: {
  columns: string[];
  mapping: ImportColumnMapping;
  sampleRows: Array<Record<string, string>>;
  analyzing: boolean;
  onChange: (mapping: ImportColumnMapping) => void;
  onApply: () => void;
  onCancel: () => void;
}) {
  const fields: Array<{ key: keyof ImportColumnMapping; label: string; required?: boolean }> = [
    { key: "date_column", label: "Data", required: true },
    { key: "description_column", label: "Descrição", required: true },
    { key: "amount_column", label: "Valor" },
    { key: "type_column", label: "Tipo (opcional)" },
    { key: "credit_column", label: "Crédito/entrada (opcional)" },
    { key: "debit_column", label: "Débito/saída (opcional)" },
  ];
  return (
    <div className="space-y-5">
      <div className="flex gap-3 rounded-xl border border-amber-500/20 bg-amber-500/10 p-4 text-sm text-amber-200">
        <AlertTriangle className="shrink-0" size={18} />
        <p>Não foi possível identificar todas as colunas com segurança. Confirme o mapeamento antes da análise.</p>
      </div>
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {fields.map((field) => (
          <label key={field.key} className="space-y-1.5 text-sm">
            <span className="text-zinc-400">{field.label}{field.required ? " *" : ""}</span>
            <select value={mapping[field.key] ?? ""} onChange={(event) => onChange({ ...mapping, [field.key]: event.target.value || null })} className="w-full rounded-xl border border-zinc-800 bg-zinc-900 px-3 py-2.5 focus:border-emerald-500 focus:outline-none">
              <option value="">Não usar</option>
              {columns.map((column) => <option key={column} value={column}>{column}</option>)}
            </select>
          </label>
        ))}
      </div>
      {sampleRows.length > 0 && (
        <div className="overflow-x-auto rounded-xl border border-zinc-800">
          <table className="min-w-full text-xs">
            <thead className="bg-zinc-900 text-zinc-500"><tr>{columns.map((column) => <th key={column} className="p-2 text-left">{column}</th>)}</tr></thead>
            <tbody>{sampleRows.slice(0, 3).map((row, index) => <tr key={index} className="border-t border-zinc-800">{columns.map((column) => <td key={column} className="max-w-48 truncate p-2 text-zinc-300">{row[column]}</td>)}</tr>)}</tbody>
          </table>
        </div>
      )}
      <div className="flex justify-end gap-2">
        <button onClick={onCancel} className="rounded-xl border border-zinc-700 px-4 py-2.5 text-sm text-zinc-300">Cancelar</button>
        <button onClick={onApply} disabled={analyzing} className="rounded-xl bg-emerald-500 px-5 py-2.5 font-semibold text-emerald-950 disabled:opacity-50">{analyzing ? "Analisando..." : "Analisar com este mapeamento"}</button>
      </div>
    </div>
  );
}

function PreviewTableRow({ row, edit, onChange }: { row: ImportPreviewRow; edit?: RowEdit; onChange: (change: Partial<RowEdit>) => void }) {
  const invalid = row.status === "invalid";
  const awaitingType = row.status === "needs_review" && !edit?.type;
  const status = row.status === "ready" ? "Pronta" : row.status === "possible_duplicate" ? "Possível duplicada" : row.status === "needs_review" ? "Escolha o tipo" : "Inválida";
  return (
    <tr className="border-t border-zinc-800 align-top">
      <td className="p-3"><input type="checkbox" disabled={invalid || awaitingType} checked={edit?.included ?? false} onChange={(event) => onChange({ included: event.target.checked })} aria-label={`Selecionar ${row.description}`} /></td>
      <td className="whitespace-nowrap p-3 text-zinc-400">{row.date ? formatDate(row.date) : "—"}</td>
      <td className="min-w-48 p-3"><input disabled={invalid} value={edit?.description ?? row.description} onChange={(event) => onChange({ description: event.target.value })} className="w-full border-b border-transparent bg-transparent focus:border-emerald-500 focus:outline-none disabled:text-zinc-500" /></td>
      <td className="p-3 text-zinc-400">{row.status === "needs_review" || !row.type ? <select disabled={invalid} value={edit?.type ?? ""} onChange={(event) => onChange({ type: event.target.value as RowEdit["type"], included: false })} className="rounded-lg border border-zinc-700 bg-zinc-900 px-2 py-1.5 focus:border-emerald-500 focus:outline-none"><option value="">Selecione</option><option value="income">Entrada</option><option value="expense">Saída</option></select> : row.type === "income" ? "Entrada" : "Saída"}</td>
      <td className="whitespace-nowrap p-3 text-right">{row.amount == null ? "—" : row.amount.toLocaleString("pt-BR", { style: "currency", currency: "BRL" })}</td>
      <td className="min-w-40 p-3"><input disabled={invalid} value={edit?.category ?? ""} onChange={(event) => onChange({ category: event.target.value })} className="w-full border-b border-transparent bg-transparent focus:border-emerald-500 focus:outline-none disabled:text-zinc-500" /></td>
      <td className="p-3"><span className={`whitespace-nowrap rounded-full border px-2 py-1 text-xs ${row.status === "ready" ? "border-emerald-500/20 bg-emerald-500/10 text-emerald-400" : row.status === "possible_duplicate" || row.status === "needs_review" ? "border-amber-500/20 bg-amber-500/10 text-amber-300" : "border-red-500/20 bg-red-500/10 text-red-300"}`} title={row.error_reason ?? undefined}>{status}</span>{(invalid || row.status === "needs_review") && row.error_reason && <p className="mt-1 max-w-52 text-xs text-zinc-500">{row.error_reason}</p>}</td>
    </tr>
  );
}

function createInitialEdits(rows: ImportPreviewRow[]): Record<number, RowEdit> {
  return Object.fromEntries(rows.map((row) => [row.id, {
    included: row.status === "ready",
    description: row.description,
    category: row.category || "",
    type: row.type || "",
  }]));
}

function formatDate(value: string): string {
  const [year, month, day] = value.slice(0, 10).split("-");
  return year && month && day ? `${day}/${month}/${year}` : value;
}
