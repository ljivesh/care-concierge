import { Skeleton } from "@/components/ui/skeleton";

/** Shown while a saved conversation is being loaded. */
export function ChatSkeleton() {
  return (
    <div aria-label="Loading conversation" className="flex flex-col gap-6 py-4" role="status">
      <Skeleton className="ml-auto h-9 w-56 rounded-2xl" />
      <div className="space-y-2">
        <Skeleton className="h-4 w-4/5" />
        <Skeleton className="h-4 w-3/5" />
      </div>
      <Skeleton className="ml-auto h-9 w-40 rounded-2xl" />
      <div className="space-y-2">
        <Skeleton className="h-4 w-2/3" />
        <Skeleton className="h-4 w-1/2" />
      </div>
    </div>
  );
}
