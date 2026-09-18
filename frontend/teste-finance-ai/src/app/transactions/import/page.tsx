"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import {
  UploadCloud,
  FileText,
  CheckCircle2,
  AlertTriangle,
  Copy,
  ArrowLeft,
  Loader2,
  History,
} from "lucide-react";
import { AppLayout } from "@/components/AppLayout";
import { useToast } from "@/contexts/ToastContext";
import { useHandleFetchError } from "@/hooks/useHandleFetchError";
import { getStorageMode, subscribeStorageMode, storage, type StorageMode } from "@/lib/storage";
import {
  type ImportBatchSummary,
  type ImportPreviewResponse,
  type ImportPreviewRow,
} from "@/lib/api";

type RowEdit = {
  included: boolean;
  category: string;
  description: string;
};

function formatCurrency(value: number) {
  return value.toLocaleString("pt-BR", { style: "currency", currency: "BRL" });
}

function formatDate(iso: string) {
  // Evita problema de fuso do `new Date("YYYY-MM-DD")` (que
  // interpretaria como UTC meia-noite e poderia exibir o dia
  // anterior dependendo do fuso do navegador).
  const [year, month, day] = iso.split("-");
  return `${day}/${month}/${year}`;
}

const STATUS_BADGE: Record<ImportPreviewRow["status"], { label: string; className: string }> = {
  new: { label: "Nova", className: "bg-emerald-500/10 text-emerald-400 border-emerald-500/20" },
  duplicated: { label: "Duplicada", className: "bg-amber-500/10 text-amber-400 border-amber-500/20" },
  error: { label: "Erro", className: "bg-red-500/10 text-red-400 border-red-500/20" },
};

export default function ImportTransactionsPage() {
  const { addToast } = useToast();
  const handleFetchError = useHandleFetchError();
  const fileInputRef = useRef<HTMLInputElement>(null);

  const [storageMode, setStorageMode] = useState<StorageMode | null>(getStorageMode());
  const [isDragging, setIsDragging] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [confirming, setConfirming] = useState(false);
  const [preview, setPreview] = useState<ImportPreviewResponse | null>(null);
  const [edits, setEdits] = useState<Record<number, RowEdit>>({});
  const [result, setResult] = useState<{ imported: number; skipped: number } | null>(null);
  const [batches, setBatches] = useState<ImportBatchSummary[]>([]);
  const [loadingBatches, setLoadingBatches] = useState(false);

  useEffect(() => subscribeStorageMode(setStorageMode), []);

  const loadBatches = useCallback(async () => {
    setLoadingBatches(true);
    try {
      const data = await storage.getImportBatches();
      setBatches(data);
    } catch {
      // Histórico é um extra — se falhar, a tela de importação
      // continua funcionando normalmente sem ele.
    } finally {
      setLoadingBatches(false);
    }
  }, []);

  useEffect(() => {
    loadBatches();
  }, [loadBatches]);

  function resetToUpload() {
    setPreview(null);
    setEdits({});
    setResult(null);
    if (fileInputRef.current) fileInputRef.current.value = "";
  }

  async function handleFile(file: File) {
    const isValidExtension = /\.(csv|ofx)$/i.test(file.name);
    if (!isValidExtension) {
      addToast("error", "Envie um arquivo .csv ou .ofx.");
      return;
    }

    if (storageMode === "local" && /\.ofx$/i.test(file.name)) {
      addToast(
        "error",
        "Arquivos .ofx ainda exigem conexão com a internet. No modo offline, use um extrato .csv.",
      );
      return;
    }

    setUploading(true);
    setResult(null);
    try {
      const data = await storage.previewImport(file);
      setPreview(data);

      const initialEdits: Record<number, RowEdit> = {};
      for (const row of data.rows) {
        initialEdits[row.id] = {
          // Duplicadas começam desmarcadas (o usuário decide se são
          // legítimas); erros nunca são selecionáveis.
          included: row.status === "new",
          category: row.category || "",
          description: row.description,
        };
      }
      setEdits(initialEdits);
    } catch (err) {
      await handleFetchError(err, "Erro ao processar o extrato:");
    } finally {
      setUploading(false);
    }
  }

  function handleDrop(e: React.DragEvent<HTMLDivElement>) {
    e.preventDefault();
    setIsDragging(false);
    const file = e.dataTransfer.files?.[0];
    if (file) handleFile(file);
  }

  function updateEdit(id: number, patch: Partial<RowEdit>) {
    setEdits((prev) => ({ ...prev, [id]: { ...prev[id], ...patch } }));
  }

  const includedCount = Object.values(edits).filter((e) => e.included).length;

  async function handleConfirm() {
    if (!preview) return;

    const rows = preview.rows
      .filter((row) => row.status !== "error" && edits[row.id]?.included)
      .map((row) => ({
        staged_id: row.id,
        category: edits[row.id].category.trim() || "Sem categoria",
        description: edits[row.id].description.trim() || row.description,
      }));

    if (rows.length === 0) {
      addToast("error", "Selecione ao menos uma movimentação para importar.");
      return;
    }

    setConfirming(true);
    try {
      const response = await storage.confirmImport(preview.batch_id, rows);
      setResult({ imported: response.imported, skipped: response.skipped });
      const count = response.imported;
      addToast(
        "success",
        count === 1 ? "1 transação importada com sucesso." : `${count} transações importadas com sucesso.`,
      );
      window.dispatchEvent(new Event("transactions-changed"));
      loadBatches();
    } catch (err) {
      await handleFetchError(err, "Erro ao confirmar importação:");
    } finally {
      setConfirming(false);
    }
  }

  if (storageMode === "local") {
    return (
      <AppLayout>
        <div className="max-w-4xl mx-auto space-y-6">
          <div className="bg-amber-500/10 border border-amber-500/20 rounded-2xl p-4 flex items-start gap-3 text-sm text-amber-200">
            <AlertTriangle className="shrink-0 mt-0.5" size={18} />
            <p>
              Você está no modo offline (dados salvos só neste navegador). Extratos <strong>.csv</strong>{" "}
              funcionam normalmente aqui; arquivos <strong>.ofx</strong> ainda exigem conexão com a
              internet.
            </p>
          </div>
          {renderImportBody()}
        </div>
      </AppLayout>
    );
  }

  return <AppLayout>{renderImportBody()}</AppLayout>;

  function renderImportBody() {
    return (
      <div className="max-w-4xl mx-auto space-y-6">
        <div>
          <h1 className="text-3xl font-bold">Importar extrato</h1>
          <p className="text-zinc-400">
            {storageMode === "local"
              ? "Envie o extrato baixado do seu banco em CSV — nada é salvo até você revisar e confirmar."
              : "Envie o extrato baixado do seu banco em CSV ou OFX — nada é salvo até você revisar e confirmar."}
          </p>
        </div>

        {!preview && !result && (
          <div
            onDragOver={(e) => {
              e.preventDefault();
              setIsDragging(true);
            }}
            onDragLeave={() => setIsDragging(false)}
            onDrop={handleDrop}
            className={`rounded-2xl border-2 border-dashed p-10 text-center transition-colors ${
              isDragging
                ? "border-emerald-500 bg-emerald-500/5"
                : "border-zinc-800 bg-zinc-900/50 hover:border-zinc-700"
            }`}
          >
            {uploading ? (
              <div className="flex flex-col items-center gap-3 text-zinc-400">
                <Loader2 className="animate-spin" size={32} />
                <p>Lendo e analisando o arquivo...</p>
              </div>
            ) : (
              <>
                <UploadCloud className="mx-auto text-zinc-500 mb-4" size={40} />
                <p className="text-lg font-medium mb-1">Arraste o arquivo aqui</p>
                <p className="text-zinc-500 text-sm mb-4">ou</p>
                <button
                  onClick={() => fileInputRef.current?.click()}
                  className="px-5 py-2.5 rounded-xl bg-emerald-500 text-emerald-950 font-semibold hover:bg-emerald-400 active:scale-95 transition-all"
                >
                  Selecionar arquivo
                </button>
                <input
                  ref={fileInputRef}
                  type="file"
                  accept={storageMode === "local" ? ".csv" : ".csv,.ofx"}
                  className="hidden"
                  onChange={(e) => {
                    const file = e.target.files?.[0];
                    if (file) handleFile(file);
                  }}
                />
                <p className="text-zinc-500 text-xs mt-4">
                  {storageMode === "local" ? "Formato: CSV" : "Formatos: CSV e OFX"}
                </p>
              </>
            )}
          </div>
        )}

        {preview && !result && (
          <div className="space-y-4">
            <div className="flex items-center gap-3 bg-zinc-900/50 border border-zinc-800 rounded-2xl p-4">
              <FileText className="text-zinc-500 shrink-0" size={20} />
              <div className="min-w-0">
                <p className="font-medium truncate">{preview.filename}</p>
                <p className="text-sm text-zinc-500">
                  {preview.total} movimentações encontradas
                </p>
              </div>
            </div>

            <div className="grid grid-cols-3 gap-2 sm:gap-3">
              <div className="bg-zinc-900/50 border border-zinc-800 rounded-xl p-2.5 sm:p-4 text-center">
                <p className="text-xl sm:text-2xl font-bold text-emerald-400">{preview.new}</p>
                <p className="text-[11px] sm:text-xs text-zinc-500 mt-1">Novas</p>
              </div>
              <div className="bg-zinc-900/50 border border-zinc-800 rounded-xl p-2.5 sm:p-4 text-center">
                <p className="text-xl sm:text-2xl font-bold text-amber-400">{preview.duplicated}</p>
                <p className="text-[11px] sm:text-xs text-zinc-500 mt-1">Duplicadas</p>
              </div>
              <div className="bg-zinc-900/50 border border-zinc-800 rounded-xl p-2.5 sm:p-4 text-center">
                <p className="text-xl sm:text-2xl font-bold text-red-400">{preview.errors}</p>
                <p className="text-[11px] sm:text-xs text-zinc-500 mt-1">Com problemas</p>
              </div>
            </div>

            <div className="bg-zinc-900/50 border border-zinc-800 rounded-2xl overflow-hidden">
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b border-zinc-800 text-zinc-500 text-left">
                      <th className="p-3 w-10"></th>
                      <th className="p-3">Data</th>
                      <th className="p-3">Descrição</th>
                      <th className="p-3">Categoria</th>
                      <th className="p-3 text-right">Valor</th>
                      <th className="p-3">Status</th>
                    </tr>
                  </thead>
                  <tbody>
                    {preview.rows.map((row) => {
                      const edit = edits[row.id];
                      const badge = STATUS_BADGE[row.status];
                      const isError = row.status === "error";

                      return (
                        <tr key={row.id} className="border-b border-zinc-800/60 last:border-0">
                          <td className="p-3 align-top">
                            <input
                              type="checkbox"
                              disabled={isError}
                              checked={edit?.included ?? false}
                              onChange={(e) => updateEdit(row.id, { included: e.target.checked })}
                              aria-label={`Incluir na importação: ${row.description}`}
                              className="rounded border-zinc-700 bg-zinc-800 text-emerald-500 focus:ring-emerald-500/40 disabled:opacity-30"
                            />
                          </td>
                          <td className="p-3 align-top whitespace-nowrap text-zinc-400">
                            {row.date ? formatDate(row.date) : "—"}
                          </td>
                          <td className="p-3 align-top min-w-[180px]">
                            {isError ? (
                              <span className="text-zinc-500 italic">{row.description}</span>
                            ) : (
                              <input
                                value={edit?.description ?? ""}
                                onChange={(e) => updateEdit(row.id, { description: e.target.value })}
                                aria-label={`Descrição da transação: ${row.description}`}
                                className="w-full bg-transparent border-b border-transparent hover:border-zinc-700 focus:border-emerald-500 focus:outline-none py-0.5"
                              />
                            )}
                          </td>
                          <td className="p-3 align-top min-w-[140px]">
                            {isError ? (
                              <span className="text-zinc-600">—</span>
                            ) : (
                              <input
                                value={edit?.category ?? ""}
                                placeholder="Sem categoria"
                                onChange={(e) => updateEdit(row.id, { category: e.target.value })}
                                aria-label={`Categoria da transação: ${row.description}`}
                                className="w-full bg-transparent border-b border-transparent hover:border-zinc-700 focus:border-emerald-500 focus:outline-none py-0.5 placeholder:text-zinc-600"
                              />
                            )}
                          </td>
                          <td
                            className={`p-3 align-top text-right whitespace-nowrap font-medium ${
                              row.type === "income" ? "text-emerald-400" : "text-zinc-200"
                            }`}
                          >
                            {row.amount != null
                              ? `${row.type === "income" ? "+" : "-"} ${formatCurrency(row.amount)}`
                              : "—"}
                          </td>
                          <td className="p-3 align-top">
                            <span
                              className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs border ${badge.className}`}
                              title={row.error_reason ?? undefined}
                            >
                              {row.status === "duplicated" && <Copy size={11} />}
                              {row.status === "error" && <AlertTriangle size={11} />}
                              {badge.label}
                            </span>
                            {isError && row.error_reason && (
                              <p className="text-xs text-zinc-400 mt-1">{row.error_reason}</p>
                            )}
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            </div>

            <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 bg-zinc-900/50 border border-zinc-800 rounded-2xl p-4">
              <p className="text-sm text-zinc-400">
                {includedCount === 1 ? (
                  <>
                    <span className="font-semibold text-zinc-200">1</span> transação será adicionada.
                  </>
                ) : (
                  <>
                    <span className="font-semibold text-zinc-200">{includedCount}</span> transações serão
                    adicionadas.
                  </>
                )}
              </p>
              <div className="flex items-center gap-2">
                <button
                  onClick={resetToUpload}
                  className="px-4 py-2.5 rounded-xl border border-zinc-800 text-zinc-300 hover:border-zinc-700 transition-all text-sm font-medium"
                >
                  Cancelar
                </button>
                <button
                  onClick={handleConfirm}
                  disabled={confirming || includedCount === 0}
                  className="px-5 py-2.5 rounded-xl bg-emerald-500 text-emerald-950 font-semibold hover:bg-emerald-400 active:scale-95 transition-all disabled:opacity-50 disabled:pointer-events-none flex items-center gap-2"
                >
                  {confirming && <Loader2 className="animate-spin" size={16} />}
                  Importar {includedCount} transaç{includedCount === 1 ? "ão" : "ões"}
                </button>
              </div>
            </div>
          </div>
        )}

        {result && (
          <div className="bg-zinc-900/50 border border-zinc-800 rounded-2xl p-8 text-center space-y-4">
            <CheckCircle2 className="mx-auto text-emerald-400" size={40} />
            <div>
              <h2 className="text-xl font-bold">Importação concluída</h2>
              <p className="text-zinc-400 mt-1">
                {result.imported === 1
                  ? "1 transação adicionada ao seu histórico."
                  : `${result.imported} transações adicionadas ao seu histórico.`}
                {result.skipped > 0 && ` ${result.skipped} não puderam ser importadas.`}
              </p>
            </div>
            <div className="flex items-center justify-center gap-2">
              <button
                onClick={resetToUpload}
                className="px-4 py-2.5 rounded-xl border border-zinc-800 text-zinc-300 hover:border-zinc-700 transition-all text-sm font-medium flex items-center gap-2"
              >
                <ArrowLeft size={16} />
                Importar outro extrato
              </button>
              <a
                href="/transactions"
                className="px-4 py-2.5 rounded-xl bg-emerald-500 text-emerald-950 font-semibold hover:bg-emerald-400 active:scale-95 transition-all text-sm"
              >
                Ver no extrato
              </a>
            </div>
          </div>
        )}

        {!preview && !result && batches.length > 0 && (
          <div className="space-y-3">
            <div className="flex items-center gap-2 text-zinc-400">
              <History size={16} />
              <h2 className="text-sm font-semibold">Importações recentes</h2>
            </div>
            <div className="bg-zinc-900/50 border border-zinc-800 rounded-2xl divide-y divide-zinc-800/60">
              {batches.slice(0, 5).map((batch) => (
                <div key={batch.id} className="p-4 flex items-center justify-between gap-4">
                  <div className="min-w-0">
                    <p className="font-medium truncate">{batch.filename}</p>
                    <p className="text-xs text-zinc-500">
                      {new Date(batch.created_at).toLocaleDateString("pt-BR")} ·{" "}
                      {batch.status === "completed" ? "Concluída" : "Não confirmada"}
                    </p>
                  </div>
                  <div className="text-right text-xs text-zinc-500 shrink-0">
                    <p className="text-emerald-400">{batch.imported_count || batch.new_count} novas</p>
                    <p>{batch.duplicated_count} duplicadas</p>
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}
        {loadingBatches && !preview && (
          <p className="text-xs text-zinc-500 text-center">Carregando histórico de importações...</p>
        )}
      </div>
    );
  }
}
