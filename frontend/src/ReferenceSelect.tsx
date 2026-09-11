import { Field } from "./components";
import { usePage } from "./state";

export function ReferenceSelect<T extends { id: string }>({
  path,
  name,
  label,
  value,
  onChange,
  render,
}: {
  path: string;
  name: string;
  label: string;
  value: string;
  onChange: (value: string) => void;
  /** Label records that have no `name`, such as environment bindings. */
  render?: (item: T) => string;
}) {
  const page = usePage<T & { name?: string }>(path);
  return (
    <div>
      <Field label={label}>
        <select
          name={name}
          required
          value={value}
          onChange={(e) => onChange(e.target.value)}
        >
          <option value="">Select {label.toLowerCase()}</option>
          {value && !page.data?.items.some((item) => item.id === value) && (
            <option value={value}>{value}</option>
          )}
          {page.data?.items.map((item) => (
            <option key={item.id} value={item.id}>
              {render ? render(item) : item.name}
            </option>
          ))}
        </select>
      </Field>
      {page.error && <small role="alert">{page.error.message}</small>}
      {(page.page > 1 || page.data?.next_cursor) && (
        <div className="option-pages">
          <button
            type="button"
            className="text-button"
            disabled={page.page === 1 || page.loading}
            onClick={page.previous}
          >
            Previous options
          </button>
          <button
            type="button"
            className="text-button"
            disabled={!page.data?.next_cursor || page.loading}
            onClick={page.next}
          >
            More options
          </button>
        </div>
      )}
    </div>
  );
}
