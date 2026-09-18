"use client";

import { useMemo, useState } from "react";
import { Check, Filter } from "lucide-react";
import {
  Button,
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
  Input,
} from "@/components/ui";
import { cn } from "@/lib/cn";
import {
  NOTIFICATION_CATEGORY_LABEL,
  NOTIFICATION_PRIORITY_LABEL,
  NOTIFICATION_STATUS_LABEL,
} from "../constants";
import {
  NotificationCategory,
  NotificationPriority,
  NotificationStatus,
} from "../types";

type SelectOption<T extends string> = {
  value: T | undefined;
  label: string;
};

export type NotificationFiltersValue = {
  category?: NotificationCategory;
  priority?: NotificationPriority;
  status?: NotificationStatus;
  from?: string;
  to?: string;
};

export type NotificationFiltersProps = NotificationFiltersValue & {
  onChange: (next: NotificationFiltersValue) => void;
  onClear: () => void;
  className?: string;
};

function FilterDropdown<T extends string>({
  label,
  value,
  options,
  onSelect,
  className,
}: {
  label: string;
  value: T | undefined;
  options: SelectOption<T>[];
  onSelect: (next: T | undefined) => void;
  className?: string;
}) {
  const selectedLabel = options.find((o) => o.value === value)?.label ?? "Todos";

  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button
          variant="outline"
          size="sm"
          className={cn("justify-between gap-2", className)}
          aria-label={label}
        >
          <span className="truncate">{selectedLabel}</span>
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="start">
        {options.map((option) => (
          <DropdownMenuItem
            key={option.value ?? "all"}
            onSelect={() => onSelect(option.value)}
            className="flex items-center justify-between gap-3"
          >
            <span>{option.label}</span>
            {option.value === value ? <Check size={16} /> : null}
          </DropdownMenuItem>
        ))}
      </DropdownMenuContent>
    </DropdownMenu>
  );
}

export function NotificationFilters({
  category,
  priority,
  status,
  from,
  to,
  onChange,
  onClear,
  className,
}: NotificationFiltersProps) {
  const [open, setOpen] = useState(false);

  const categoryOptions = useMemo<SelectOption<NotificationCategory>[]>(() => {
    return [
      { value: undefined, label: "Todas as categorias" },
      ...Object.values(NotificationCategory).map((value) => ({
        value,
        label: NOTIFICATION_CATEGORY_LABEL[value],
      })),
    ];
  }, []);

  const priorityOptions = useMemo<SelectOption<NotificationPriority>[]>(() => {
    return [
      { value: undefined, label: "Todas as prioridades" },
      ...Object.values(NotificationPriority).map((value) => ({
        value,
        label: NOTIFICATION_PRIORITY_LABEL[value],
      })),
    ];
  }, []);

  const statusOptions = useMemo<SelectOption<NotificationStatus>[]>(() => {
    return [
      { value: undefined, label: "Todos os status" },
      ...Object.values(NotificationStatus).map((value) => ({
        value,
        label: NOTIFICATION_STATUS_LABEL[value],
      })),
    ];
  }, []);

  const content = (
    <div className="grid grid-cols-1 md:grid-cols-5 gap-2">
      <FilterDropdown
        label="Filtrar por status"
        value={status}
        options={statusOptions}
        onSelect={(next) => onChange({ category, priority, status: next, from, to })}
        className="w-full"
      />
      <FilterDropdown
        label="Filtrar por categoria"
        value={category}
        options={categoryOptions}
        onSelect={(next) => onChange({ category: next, priority, status, from, to })}
        className="w-full"
      />
      <FilterDropdown
        label="Filtrar por prioridade"
        value={priority}
        options={priorityOptions}
        onSelect={(next) => onChange({ category, priority: next, status, from, to })}
        className="w-full"
      />

      <Input
        type="date"
        value={from ?? ""}
        onChange={(e) => onChange({ category, priority, status, from: e.target.value || undefined, to })}
        aria-label="Data inicial"
      />
      <Input
        type="date"
        value={to ?? ""}
        onChange={(e) => onChange({ category, priority, status, from, to: e.target.value || undefined })}
        aria-label="Data final"
      />

      <div className="md:col-span-5 flex items-center justify-between gap-2">
        <Button
          variant="ghost"
          size="sm"
          onClick={onClear}
          aria-label="Limpar filtros"
        >
          Limpar
        </Button>
      </div>
    </div>
  );

  return (
    <div className={cn(className)}>
      <div className="hidden md:block">{content}</div>

      <div className="md:hidden">
        <Dialog open={open} onOpenChange={setOpen}>
          <Button
            variant="outline"
            size="sm"
            onClick={() => setOpen(true)}
            className="w-full justify-center gap-2"
            aria-label="Abrir filtros"
          >
            <Filter size={16} />
            Filtros
          </Button>
          <DialogContent
            className="left-auto right-0 top-0 h-dvh w-[420px] max-w-[calc(100%-1.5rem)] translate-x-0 translate-y-0 rounded-none"
            aria-label="Filtros de notificações"
          >
            <DialogHeader>
              <DialogTitle>Filtros</DialogTitle>
            </DialogHeader>
            <div className="my-4 h-px bg-border" />
            {content}
            <Button onClick={() => setOpen(false)} aria-label="Fechar filtros">
              Aplicar
            </Button>
          </DialogContent>
        </Dialog>
      </div>
    </div>
  );
}
