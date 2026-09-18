"use client";

import { Skeleton } from "@/components/ui";
import { cn } from "@/lib/cn";

export type NotificationSkeletonProps = {
  rows?: number;
  className?: string;
};

export function NotificationSkeleton({
  rows = 6,
  className,
}: NotificationSkeletonProps) {
  return (
    <div className={cn("space-y-3", className)} aria-label="Carregando notificações">
      {Array.from({ length: rows }).map((_, index) => (
        <div
          key={index}
          className="rounded-lg border border-border bg-card p-6 space-y-3"
        >
          <div className="flex items-center gap-2">
            <Skeleton className="h-5 w-24 rounded-full" />
            <Skeleton className="h-5 w-20 rounded-full" />
            <Skeleton className="h-5 w-16 rounded-full" />
          </div>
          <Skeleton className="h-5 w-3/4" />
          <Skeleton className="h-4 w-1/3" />
          <div className="flex gap-2 pt-2">
            <Skeleton className="h-9 w-24 rounded-md" />
            <Skeleton className="h-9 w-32 rounded-md" />
          </div>
        </div>
      ))}
    </div>
  );
}

