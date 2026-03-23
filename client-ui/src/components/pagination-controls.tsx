import Link from "next/link";
import type { ReactNode } from "react";

const PAGE_SIZE_OPTIONS = [10, 25, 50] as const;

type PaginationControlsProps = {
  pathname: string;
  query?: Record<string, string | undefined>;
  currentPage: number;
  pageSize: number;
  totalItems: number;
  itemLabel: string;
};

export function PaginationControls({
  pathname,
  query = {},
  currentPage,
  pageSize,
  totalItems,
  itemLabel,
}: PaginationControlsProps) {
  const totalPages = Math.max(1, Math.ceil(totalItems / pageSize));
  const startItem = totalItems === 0 ? 0 : (currentPage - 1) * pageSize + 1;
  const endItem = totalItems === 0 ? 0 : Math.min(totalItems, currentPage * pageSize);
  const pageNumbers = buildPageWindow(currentPage, totalPages);

  return (
    <div className="flex flex-col gap-4 rounded-[22px] border border-[rgba(24,24,27,0.08)] bg-white/55 px-4 py-4 sm:px-5">
      <div className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
        <div>
          <p className="text-sm font-semibold text-[#111827]">
            Showing {startItem}-{endItem} of {totalItems} {itemLabel}
          </p>
          <p className="mt-1 text-xs uppercase tracking-[0.14em] text-[#8f735c]">
            Page {currentPage} of {totalPages}
          </p>
        </div>

        <form action={pathname} className="flex items-center gap-2">
          {Object.entries(query).map(([key, value]) =>
            value ? <input key={key} type="hidden" name={key} value={value} /> : null,
          )}
          <input type="hidden" name="page" value="1" />
          <label className="text-xs font-semibold uppercase tracking-[0.14em] text-[#8f735c]">
            Page size
          </label>
          <select
            name="page_size"
            defaultValue={String(pageSize)}
            className="vault-input rounded-full px-3 py-2 text-sm text-[#111827]"
          >
            {PAGE_SIZE_OPTIONS.map((option) => (
              <option key={option} value={option}>
                {option}
              </option>
            ))}
          </select>
          <button
            type="submit"
            className="ops-button-secondary rounded-full px-4 py-2 text-sm font-semibold"
          >
            Apply
          </button>
        </form>
      </div>

      <div className="flex flex-wrap items-center gap-2">
        <PaginationLink
          href={buildPageHref(pathname, query, Math.max(1, currentPage - 1), pageSize)}
          disabled={currentPage <= 1}
        >
          Previous
        </PaginationLink>

        {pageNumbers.map((pageNumber, index) =>
          pageNumber === "ellipsis" ? (
            <span
              key={`ellipsis-${index}`}
              className="px-2 text-sm font-semibold text-[#8f735c]"
            >
              ...
            </span>
          ) : (
            <PaginationLink
              key={pageNumber}
              href={buildPageHref(pathname, query, pageNumber, pageSize)}
              active={pageNumber === currentPage}
            >
              {String(pageNumber)}
            </PaginationLink>
          ),
        )}

        <PaginationLink
          href={buildPageHref(pathname, query, Math.min(totalPages, currentPage + 1), pageSize)}
          disabled={currentPage >= totalPages}
        >
          Next
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
}: {
  href: string;
  children: ReactNode;
  active?: boolean;
  disabled?: boolean;
}) {
  const className = active
    ? "rounded-full bg-[#111827] px-4 py-2 text-sm font-semibold text-white"
    : "rounded-full border border-[rgba(24,24,27,0.08)] bg-white px-4 py-2 text-sm font-semibold text-[#111827] transition hover:border-[rgba(255,106,61,0.3)] hover:text-[#b9482a]";

  if (disabled) {
    return (
      <span
        aria-disabled="true"
        className="rounded-full border border-[rgba(24,24,27,0.06)] bg-[rgba(24,24,27,0.03)] px-4 py-2 text-sm font-semibold text-[#9ca3af]"
      >
        {children}
      </span>
    );
  }

  return (
    <Link href={href} className={className}>
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
    if (value) {
      searchParams.set(key, value);
    }
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
