import Link from "next/link";
import type { ReactNode } from "react";

type PaginationControlsProps = {
  pathname: string;
  query?: Record<string, string | undefined>;
  currentPage: number;
  pageSize: number;
  totalItems: number;
  itemLabel: string;
  /** Dark styling for pages on the charcoal dashboard background. */
  variant?: "light" | "dark";
};

export function PaginationControls({
  pathname,
  query = {},
  currentPage,
  pageSize,
  totalItems,
  itemLabel,
  variant = "light",
}: PaginationControlsProps) {
  const totalPages = Math.max(1, Math.ceil(totalItems / pageSize));
  const startItem = totalItems === 0 ? 0 : (currentPage - 1) * pageSize + 1;
  const endItem = totalItems === 0 ? 0 : Math.min(totalItems, currentPage * pageSize);
  const pageNumbers = buildPageWindow(currentPage, totalPages);
  const dark = variant === "dark";

  return (
    <div className="flex items-center justify-between gap-4">
      <p className={dark ? "text-xs text-white/45" : "text-xs text-[#6b7280]"}>
        <span className={dark ? "font-medium text-white/80" : "font-medium text-[#374151]"}>
          {startItem}–{endItem}
        </span>{" "}
        of{" "}
        <span className={dark ? "font-medium text-white/80" : "font-medium text-[#374151]"}>
          {totalItems}
        </span>{" "}
        {itemLabel}
      </p>

      <div className="flex items-center gap-1">
        <PaginationLink
          variant={variant}
          href={buildPageHref(pathname, query, Math.max(1, currentPage - 1), pageSize)}
          disabled={currentPage <= 1}
        >
          ←
        </PaginationLink>

        {pageNumbers.map((pageNumber, index) =>
          pageNumber === "ellipsis" ? (
            <span
              key={`ellipsis-${index}`}
              className={dark ? "px-1 text-xs text-white/35" : "px-1 text-xs text-[#9ca3af]"}
            >
              …
            </span>
          ) : (
            <PaginationLink
              key={pageNumber}
              variant={variant}
              href={buildPageHref(pathname, query, pageNumber, pageSize)}
              active={pageNumber === currentPage}
            >
              {String(pageNumber)}
            </PaginationLink>
          ),
        )}

        <PaginationLink
          variant={variant}
          href={buildPageHref(pathname, query, Math.min(totalPages, currentPage + 1), pageSize)}
          disabled={currentPage >= totalPages}
        >
          →
        </PaginationLink>
      </div>
    </div>
  );
}

function PaginationLink({
  href,
  children,
  active = false,
  disabled = false,
  variant = "light",
}: {
  href: string;
  children: ReactNode;
  active?: boolean;
  disabled?: boolean;
  variant?: "light" | "dark";
}) {
  const dark = variant === "dark";

  if (disabled) {
    return (
      <span
        className={`flex h-8 min-w-[2rem] items-center justify-center rounded-md px-2 text-xs ${
          dark ? "text-white/25" : "text-[#d1d5db]"
        }`}
      >
        {children}
      </span>
    );
  }

  if (active) {
    return (
      <span
        className={`flex h-8 min-w-[2rem] items-center justify-center rounded-md px-2 text-xs font-medium text-white ${
          dark ? "bg-white/15" : "bg-[#111827]"
        }`}
      >
        {children}
      </span>
    );
  }

  return (
    <Link
      href={href}
      className={`flex h-8 min-w-[2rem] items-center justify-center rounded-md px-2 text-xs font-medium transition ${
        dark
          ? "text-white/65 hover:bg-white/[0.06]"
          : "text-[#374151] hover:bg-[#f3f4f6]"
      }`}
    >
      {children}
    </Link>
  );
}

function buildPageHref(
  pathname: string,
  query: Record<string, string | undefined>,
  page: number,
  pageSize: number,
): string {
  const searchParams = new URLSearchParams();
  Object.entries(query).forEach(([key, value]) => {
    if (value) searchParams.set(key, value);
  });
  searchParams.set("page", String(page));
  searchParams.set("page_size", String(pageSize));
  const search = searchParams.toString();
  return search ? `${pathname}?${search}` : pathname;
}

function buildPageWindow(
  currentPage: number,
  totalPages: number,
): Array<number | "ellipsis"> {
  if (totalPages <= 5) {
    return Array.from({ length: totalPages }, (_, index) => index + 1);
  }
  if (currentPage <= 3) {
    return [1, 2, 3, 4, "ellipsis", totalPages];
  }
  if (currentPage >= totalPages - 2) {
    return [1, "ellipsis", totalPages - 3, totalPages - 2, totalPages - 1, totalPages];
  }
  return [1, "ellipsis", currentPage - 1, currentPage, currentPage + 1, "ellipsis", totalPages];
}
