/* =====================================================================
   02 - Carga de los CSV simulados en RiegoInteligente
   1) Descomprima datos_simulados.zip en C:\PGC\csv\  (o cambie @ruta)
   2) Ejecute este script completo (SSMS). Tarda ~1–3 min.
   Requiere SQL Server 2017+ (FORMAT = 'CSV').
   ===================================================================== */
USE RiegoInteligente;
GO
DELETE FROM dbo.EventoRiego; DELETE FROM dbo.Lectura; DELETE FROM dbo.Dispositivo;
DELETE FROM dbo.Lote; DELETE FROM dbo.Cultivo; DELETE FROM dbo.Finca; DELETE FROM dbo.Propietario;
GO
DECLARE @ruta NVARCHAR(200) = N'C:\PGC\csv\';
DECLARE @tablas TABLE (orden INT, tabla SYSNAME);
INSERT @tablas VALUES (1,'Propietario'),(2,'Finca'),(3,'Cultivo'),(4,'Lote'),(5,'Dispositivo'),(6,'Lectura'),(7,'EventoRiego');
DECLARE @t SYSNAME, @sql NVARCHAR(MAX);
DECLARE c CURSOR LOCAL FAST_FORWARD FOR SELECT tabla FROM @tablas ORDER BY orden;
OPEN c; FETCH NEXT FROM c INTO @t;
WHILE @@FETCH_STATUS = 0
BEGIN
    SET @sql = N'BULK INSERT dbo.' + QUOTENAME(@t) + N' FROM ''' + @ruta + @t + N'.csv''
        WITH (FORMAT = ''CSV'', FIRSTROW = 2, CODEPAGE = ''65001'', FIELDTERMINATOR = '','',
              ROWTERMINATOR = ''0x0a'', KEEPNULLS, TABLOCK, BATCHSIZE = 100000);';
    EXEC sp_executesql @sql;
    PRINT @t + ': ' + CAST(@@ROWCOUNT AS VARCHAR(20)) + ' filas';
    FETCH NEXT FROM c INTO @t;
END
CLOSE c; DEALLOCATE c;
GO
/* Conteos esperados:
   Propietario 7 · Finca 7 · Cultivo 7 · Lote 7 · Dispositivo 7
   Lectura 1.003.400 · EventoRiego 992 */
SELECT 'Lectura' AS tabla, COUNT_BIG(*) AS filas FROM dbo.Lectura
UNION ALL SELECT 'EventoRiego', COUNT_BIG(*) FROM dbo.EventoRiego
UNION ALL SELECT 'Dispositivo', COUNT_BIG(*) FROM dbo.Dispositivo;
