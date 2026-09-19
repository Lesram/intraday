import { Table, Input } from 'antd';
import type { ColumnsType } from 'antd/es/table';
import { useState, useMemo } from 'react';

// V13 W98 (Lens 7): the original constraint was
// ``T extends Record<string, unknown>`` which blocked typed records
// (RegimeScale, ThresholdConfig, etc.) from satisfying the index
// signature.  Relaxing to ``T extends object`` keeps the generic
// useful while letting concrete typed records pass.  The unsafe
// indexing in ``filtered`` is now narrowed via a typed helper.
interface ThresholdTableProps<T extends object> {
  data: T[];
  columns: ColumnsType<T>;
  searchField?: keyof T;
  pageSize?: number;
}

function ThresholdTable<T extends object>({
  data,
  columns,
  searchField,
  pageSize = 20,
}: ThresholdTableProps<T>) {
  const [search, setSearch] = useState('');

  const filtered = useMemo(() => {
    if (!search || !searchField) return data;
    const lower = search.toLowerCase();
    return data.filter((row) => {
      const v = (row as Record<string, unknown>)[searchField as string];
      return String(v ?? '').toLowerCase().includes(lower);
    });
  }, [data, search, searchField]);

  return (
    <div>
      {searchField && (
        <Input.Search
          placeholder={`Search by ${String(searchField)}...`}
          onChange={(e) => setSearch(e.target.value)}
          style={{ marginBottom: 12, maxWidth: 320 }}
          allowClear
        />
      )}
      <Table
        dataSource={filtered}
        columns={columns}
        size="small"
        pagination={filtered.length > pageSize ? { pageSize, showSizeChanger: true } : false}
        rowKey={(_, i) => String(i)}
        scroll={{ x: 'max-content' }}
      />
    </div>
  );
}

export default ThresholdTable;
