import { Table, Input } from 'antd';
import type { ColumnsType } from 'antd/es/table';
import { useState, useMemo } from 'react';

interface ThresholdTableProps<T extends Record<string, unknown>> {
  data: T[];
  columns: ColumnsType<T>;
  searchField?: keyof T;
  pageSize?: number;
}

function ThresholdTable<T extends Record<string, unknown>>({
  data,
  columns,
  searchField,
  pageSize = 20,
}: ThresholdTableProps<T>) {
  const [search, setSearch] = useState('');

  const filtered = useMemo(() => {
    if (!search || !searchField) return data;
    const lower = search.toLowerCase();
    return data.filter((row) => String(row[searchField]).toLowerCase().includes(lower));
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
