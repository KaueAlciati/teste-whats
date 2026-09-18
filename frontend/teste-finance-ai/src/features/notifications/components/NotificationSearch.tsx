"use client";

import { Search, X } from "lucide-react";
import { Button, Input } from "@/components/ui";
import { cn } from "@/lib/cn";

export type NotificationSearchProps = {
  value: string;
  onChange: (next: string) => void;
  placeholder?: string;
  className?: string;
};

export function NotificationSearch({
  value,
  onChange,
  placeholder = "Buscar notificações...",
  className,
}: NotificationSearchProps) {
  return (
    <div className={cn("relative", className)}>
      <Search
        size={16}
        className="absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground"
        aria-hidden="true"
      />
      <Input
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder}
        className="pl-9 pr-10"
        aria-label="Buscar notificações"
      />
      {value ? (
        <Button
          variant="ghost"
          size="icon"
          onClick={() => onChange("")}
          className="absolute right-1 top-1/2 -translate-y-1/2 h-8 w-8"
          aria-label="Limpar busca"
        >
          <X size={16} />
        </Button>
      ) : null}
    </div>
  );
}

