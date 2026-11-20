import { useMemo, useRef, useState, type ChangeEvent, type DragEvent } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import './MaterialsPage.css';

type MaterialType = 'PDF' | 'DOCX';
type MaterialStatus = 'PROCESSING' | 'READY' | 'ERROR';
type TypeFilter = 'ALL' | MaterialType;
type StatusFilter = 'ALL' | MaterialStatus;
type SortMode = 'newest' | 'oldest' | 'title' | 'size';

interface MaterialItem {
  materialId: string;
  title: string;
  typeMaterial: MaterialType;
  statusMaterial: MaterialStatus;
  materialSize: number;
  createdAt: string;
}

const MAX_FILE_SIZE = 50 * 1024 * 1024;

const UploadIcon = () => (
  <svg viewBox="0 0 24 24" fill="none" aria-hidden="true">
    <path d="M12 16V5m0 0L7.5 9.5M12 5l4.5 4.5" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" />
    <path d="M4 15.5v2A2.5 2.5 0 006.5 20h11a2.5 2.5 0 002.5-2.5v-2" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" />
  </svg>
);
const SearchIcon = () => (
  <svg viewBox="0 0 24 24" fill="none" aria-hidden="true">
    <circle cx="11" cy="11" r="6.5" stroke="currentColor" strokeWidth="1.8" />
    <path d="M16 16l4.5 4.5" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" />
  </svg>
);
const RefreshIcon = () => (
  <svg viewBox="0 0 24 24" fill="none" aria-hidden="true">
    <path d="M20 12a8 8 0 11-2.34-5.66M20 4v4.5h-4.5" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" />
  </svg>
);
const DocIcon = () => (
  <svg viewBox="0 0 36 44" fill="none" aria-hidden="true">
    <path d="M7 3.5h14.5L30 12v27a2 2 0 01-2 2H7a2 2 0 01-2-2v-33a2 2 0 012-2z" stroke="currentColor" strokeWidth="2" strokeLinejoin="round" />
    <path d="M21.5 3.5V12H30" stroke="currentColor" strokeWidth="2" strokeLinejoin="round" />
    <path d="M10.5 20h14M10.5 26h14M10.5 32h9" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
  </svg>
);
const EmptyIcon = () => (
  <svg viewBox="0 0 64 64" fill="none" aria-hidden="true">
    <path d="M14 10h24l12 12v32a4 4 0 01-4 4H14a4 4 0 01-4-4V14a4 4 0 014-4z" stroke="currentColor" strokeWidth="2.4" strokeLinejoin="round" />
    <path d="M38 10v12h12" stroke="currentColor" strokeWidth="2.4" strokeLinejoin="round" />
    <path d="M20 34h20M20 42h20M20 50h12" stroke="currentColor" strokeWidth="2.4" strokeLinecap="round" />
  </svg>
);

const STATUS_META: Record<MaterialStatus, { label: string; className: string }> = {
  READY: { label: 'Обработан', className: 'is-ready' },
  PROCESSING: { label: 'В процессе', className: 'is-processing' },
  ERROR: { label: 'Ошибка', className: 'is-error' },
};

const formatSize = (bytes: number): string => {
  if (!bytes || bytes < 0) return '—';
  const units = ['Б', 'КБ', 'МБ', 'ГБ'];
  let value = bytes;
  let unit = 0;
  while (value >= 1024 && unit < units.length - 1) { value /= 1024; unit += 1; }
  const rounded = value >= 10 || unit === 0 ? Math.round(value) : Math.round(value * 10) / 10;
  return `${rounded} ${units[unit]}`;
};

const formatDate = (iso: string): string => {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return '—';
  return date.toLocaleDateString('ru-RU', { day: '2-digit', month: '2-digit', year: 'numeric' });
};

const MaterialsPage = () => {
  const { courseId } = useParams<{ courseId: string }>();
  const navigate = useNavigate();

  // Данные (заполняются на этапе интеграции с API)
  const [materials] = useState<MaterialItem[]>([]);

  // Фильтры, сортировка, поиск
  const [query, setQuery] = useState('');
  const [typeFilter, setTypeFilter] = useState<TypeFilter>('ALL');
  const [statusFilter, setStatusFilter] = useState<StatusFilter>('ALL');
  const [sortMode, setSortMode] = useState<SortMode>('newest');
  const [selected, setSelected] = useState<Set<string>>(() => new Set());

  // Форма загрузки
  const [pendingFiles, setPendingFiles] = useState<File[]>([]);
  const [uploadError, setUploadError] = useState<string | null>(null);
  const [uploadNotice, setUploadNotice] = useState<string | null>(null);
  const [dragActive, setDragActive] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const visibleMaterials = useMemo(() => {
    const normalizedQuery = query.trim().toLowerCase();
    const filtered = materials.filter((material) => {
      if (normalizedQuery && !material.title.toLowerCase().includes(normalizedQuery)) return false;
      if (typeFilter !== 'ALL' && material.typeMaterial !== typeFilter) return false;
      if (statusFilter !== 'ALL' && material.statusMaterial !== statusFilter) return false;
      return true;
    });

    return filtered.sort((a, b) => {
      switch (sortMode) {
        case 'oldest': return new Date(a.createdAt).getTime() - new Date(b.createdAt).getTime();
        case 'title': return a.title.localeCompare(b.title, 'ru');
        case 'size': return b.materialSize - a.materialSize;
        default: return new Date(b.createdAt).getTime() - new Date(a.createdAt).getTime();
      }
    });
  }, [materials, query, typeFilter, statusFilter, sortMode]);

  const filtersActive = query.trim() !== '' || typeFilter !== 'ALL' || statusFilter !== 'ALL' || sortMode !== 'newest';
  const allVisibleSelected = visibleMaterials.length > 0 && visibleMaterials.every((m) => selected.has(m.materialId));

  const toggleSelectAll = () => {
    setSelected((prev) => {
      const next = new Set(prev);
      if (allVisibleSelected) visibleMaterials.forEach((m) => next.delete(m.materialId));
      else visibleMaterials.forEach((m) => next.add(m.materialId));
      return next;
    });
  };
  const toggleSelect = (id: string) => {
    setSelected((prev) => { const next = new Set(prev); if (next.has(id)) next.delete(id); else next.add(id); return next; });
  };
  const resetFilters = () => { setQuery(''); setTypeFilter('ALL'); setStatusFilter('ALL'); setSortMode('newest'); };

  const onPickClick = () => fileInputRef.current?.click();
  const addFiles = (files: FileList | File[]) => {
    const incoming = Array.from(files);
    if (!incoming.length) return;
    const accepted: File[] = []; const problems: string[] = [];
    incoming.forEach((file) => {
      const extension = file.name.split('.').pop()?.toLowerCase() ?? '';
      if (extension !== 'pdf' && extension !== 'docx') problems.push(`${file.name} — только PDF или DOCX`);
      else if (file.size === 0) problems.push(`${file.name} — пустой файл`);
      else if (file.size > MAX_FILE_SIZE) problems.push(`${file.name} — больше 50 МБ`);
      else accepted.push(file);
    });
    if (accepted.length) { setPendingFiles((prev) => [...prev, ...accepted]); setUploadNotice(null); }
    setUploadError(problems.length ? problems.join('; ') : null);
  };
  const removePendingFile = (index: number) => setPendingFiles((prev) => prev.filter((_, i) => i !== index));
  const handleFileInput = (event: ChangeEvent<HTMLInputElement>) => { if (event.target.files) addFiles(event.target.files); event.target.value = ''; };
  const handleDragOver = (event: DragEvent<HTMLDivElement>) => { event.preventDefault(); if (!dragActive) setDragActive(true); };
  const handleDragLeave = (event: DragEvent<HTMLDivElement>) => { event.preventDefault(); const n = event.relatedTarget as Node | null; if (n && event.currentTarget.contains(n)) return; setDragActive(false); };
  const handleDrop = (event: DragEvent<HTMLDivElement>) => { event.preventDefault(); setDragActive(false); if (event.dataTransfer.files) addFiles(event.dataTransfer.files); };
  const handleUpload = () => {
    if (!pendingFiles.length) return;
    setUploadNotice(`Подготовлено файлов: ${pendingFiles.length}. Отправка на сервер будет подключена на этапе интеграции с API.`);
    setUploadError(null);
  };

  if (!courseId) {
    return (
      <div className="materials-page"><div className="materials-page__pattern" aria-hidden="true" /><div className="materials-page__content"><div className="materials-state is-error"><p>Курс не найден</p><span>Вернитесь к списку курсов и откройте материалы нужного курса.</span><button type="button" className="materials-state__retry" onClick={() => navigate('/courses')}>Ко всем курсам</button></div></div></div>
    );
  }

  return (
    <div className="materials-page">
      <div className="materials-page__pattern" aria-hidden="true" />
      <div className="materials-page__content">
        <section className="materials-block">
          <div className="materials-tab">Загрузка материала</div>
          <div className="materials-panel materials-panel--upload">
            <div className={`upload-zone${dragActive ? ' is-dragging' : ''}`} onClick={onPickClick} onDragEnter={handleDragOver} onDragOver={handleDragOver} onDragLeave={handleDragLeave} onDrop={handleDrop}>
              <input ref={fileInputRef} type="file" accept=".pdf,.docx,application/pdf,application/vnd.openxmlformats-officedocument.wordprocessingml.document" multiple className="upload-zone__input" onChange={handleFileInput} tabIndex={-1} />
              <span className="upload-zone__icon"><UploadIcon /></span>
              <h2 className="upload-zone__title">Загрузите материалы</h2>
              <p className="upload-zone__hint">Перетащите файлы сюда или выберите на устройстве</p>
              <p className="upload-zone__formats">PDF или DOCX · до 50 МБ</p>
              {pendingFiles.length > 0 && (
                <ul className="upload-zone__files" onClick={(e) => e.stopPropagation()}>
                  {pendingFiles.map((file, index) => (
                    <li key={`${file.name}-${file.lastModified}-${index}`} className="upload-zone__file">
                      <span className="upload-zone__file-name" title={file.name}>{file.name}</span>
                      <span className="upload-zone__file-size">{formatSize(file.size)}</span>
                      <button type="button" className="upload-zone__file-remove" onClick={() => removePendingFile(index)} aria-label={`Убрать ${file.name}`}>×</button>
                    </li>
                  ))}
                </ul>
              )}
              <div className="upload-zone__actions" onClick={(e) => e.stopPropagation()}>
                <button type="button" className="materials-btn materials-btn--outline" onClick={onPickClick}>Выберите файлы</button>
                {pendingFiles.length > 0 && <button type="button" className="materials-btn materials-btn--primary" onClick={handleUpload}>Загрузить{pendingFiles.length > 1 ? ` (${pendingFiles.length})` : ''}</button>}
              </div>
            </div>
            {(uploadError || uploadNotice) && <div className={`upload-message${uploadError ? ' is-error' : ' is-success'}`} role="status">{uploadError ?? uploadNotice}</div>}
          </div>
        </section>

        <section className="materials-block">
          <div className="materials-tab">Материалы <span className="materials-tab__count">{materials.length}</span></div>
          <div className="materials-panel materials-panel--list">
            <div className="materials-filters">
              <label className="materials-search">
                <span className="materials-search__icon"><SearchIcon /></span>
                <input type="search" value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Поиск по названию" aria-label="Поиск материалов по названию" />
                {query && <button type="button" className="materials-search__clear" onClick={() => setQuery('')} aria-label="Очистить поиск">×</button>}
              </label>
              <select className="materials-filter" value={typeFilter} onChange={(e) => setTypeFilter(e.target.value as TypeFilter)} aria-label="Фильтр по типу материала">
                <option value="ALL">Все типы</option><option value="PDF">PDF</option><option value="DOCX">DOCX</option>
              </select>
              <select className="materials-filter" value={statusFilter} onChange={(e) => setStatusFilter(e.target.value as StatusFilter)} aria-label="Фильтр по статусу материала">
                <option value="ALL">Все статусы</option><option value="READY">Обработан</option><option value="PROCESSING">В процессе</option><option value="ERROR">Ошибка</option>
              </select>
              <select className="materials-filter" value={sortMode} onChange={(e) => setSortMode(e.target.value as SortMode)} aria-label="Сортировка материалов">
                <option value="newest">Сначала новые</option><option value="oldest">Сначала старые</option><option value="title">По названию</option><option value="size">По размеру</option>
              </select>
              <button type="button" className={`materials-filter materials-filter--reset${filtersActive ? ' is-active' : ''}`} onClick={resetFilters} disabled={!filtersActive}>Сбросить фильтры</button>
            </div>

            <div className="materials-toolbar">
              <div className="materials-toolbar__search">
                <input type="search" value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Поиск по названию" aria-label="Быстрый поиск материалов" />
              </div>
              <button type="button" className="materials-toolbar__apply" title="Обновить список"><span className="materials-toolbar__apply-icon"><RefreshIcon /></span>Обновить</button>
              {selected.size > 0 && <span className="materials-toolbar__selected">Выбрано: {selected.size}</span>}
            </div>

            <div className="materials-table-wrap">
              {visibleMaterials.length === 0 ? (
                <div className="materials-state">
                  <span className="materials-state__icon"><EmptyIcon /></span>
                  <p>{materials.length === 0 ? 'Материалов пока нет' : 'Ничего не найдено'}</p>
                  <span>{materials.length === 0 ? 'Загрузите первый PDF или DOCX — он появится в этом списке.' : 'Попробуйте изменить поисковый запрос или сбросить фильтры.'}</span>
                </div>
              ) : (
                <table className="materials-table">
                  <thead>
                    <tr>
                      <th className="col-check"><input type="checkbox" checked={allVisibleSelected} onChange={toggleSelectAll} aria-label="Выбрать все материалы" /></th>
                      <th>Название</th><th className="col-type">Тип</th><th className="col-size">Размер</th><th className="col-date">Дата загрузки</th><th className="col-status">Статус</th><th className="col-actions">Действия</th>
                    </tr>
                  </thead>
                  <tbody>
                    {visibleMaterials.map((material) => {
                      const meta = STATUS_META[material.statusMaterial];
                      return (
                        <tr key={material.materialId} className={selected.has(material.materialId) ? 'is-selected' : undefined}>
                          <td className="col-check"><input type="checkbox" checked={selected.has(material.materialId)} onChange={() => toggleSelect(material.materialId)} aria-label={`Выбрать ${material.title}`} /></td>
                          <td><div className="material-name"><span className="material-file-icon"><DocIcon /></span><button type="button" className="material-name__title" title={material.title}>{material.title}</button></div></td>
                          <td className="col-type"><span className="material-type-pill">{material.typeMaterial}</span></td>
                          <td className="col-size">{formatSize(material.materialSize)}</td>
                          <td className="col-date">{formatDate(material.createdAt)}</td>
                          <td className="col-status"><span className={`material-status ${meta.className}`}>{meta.label}</span></td>
                          <td className="col-actions"><span className="materials-placeholder" style={{ minHeight: 0, fontSize: 12 }}>Действия будут доступны после интеграции с API</span></td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              )}
            </div>

            <div className="materials-panel__footer">
              <span>Показано {visibleMaterials.length} из {materials.length}</span>
            </div>
          </div>
        </section>
      </div>
    </div>
  );
};

export default MaterialsPage;
