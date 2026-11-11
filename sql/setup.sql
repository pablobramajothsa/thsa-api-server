-- =============================================================================
-- setup.sql - Usuario de solo lectura para la API (Oracle 11g R2)
--
-- PARA REVISIÓN Y EJECUCIÓN DE UN DBA. No contiene secretos: la contraseña se
-- pide de forma interactiva. Ejecutar en SQL*Plus / SQLcl como usuario con
-- privilegios de DBA:
--
--     sqlplus / as sysdba @sql/setup.sql
--
-- Ajustar las variables DEFINE antes de ejecutar.
-- =============================================================================

SET VERIFY OFF
SET ECHO ON
WHENEVER SQLERROR EXIT SQL.SQLCODE ROLLBACK

-- Esquema dueño de las vistas publicadas (placeholder).
DEFINE owner_schema = APP_OWNER
DEFINE api_user     = API_READONLY
DEFINE api_profile  = API_READONLY_PROFILE

ACCEPT api_password CHAR PROMPT 'Contraseña para &&api_user: ' HIDE

-- -----------------------------------------------------------------------------
-- 1. Los límites de recursos de un PROFILE (SESSIONS_PER_USER, CPU_PER_CALL...)
--    solo se aplican si RESOURCE_LIMIT = TRUE. En 11g el valor por defecto es
--    FALSE. Verificar antes de cambiarlo: afecta a todos los profiles de la base.
-- -----------------------------------------------------------------------------
-- SHOW PARAMETER resource_limit
ALTER SYSTEM SET RESOURCE_LIMIT = TRUE SCOPE = BOTH;

-- -----------------------------------------------------------------------------
-- 2. PROFILE con límites de sesiones y consumo por llamada.
--    SESSIONS_PER_USER: el pool de la API usa hasta DB_POOL_MAX (10) por proceso
--      más margen. Si se corren N workers/instancias, usar N * 10 + 2.
--    CPU_PER_CALL: en centésimas de segundo (500 = 5 s), alineado con
--      DB_CALL_TIMEOUT_MS = 5000.
--    LOGICAL_READS_PER_CALL: corta consultas que lean demasiados bloques.
--    IDLE_TIME: UNLIMITED a propósito; el pool mantiene conexiones abiertas
--      y un IDLE_TIME corto las cortaría (el pool hace ping cada 60 s).
-- -----------------------------------------------------------------------------
CREATE PROFILE &&api_profile LIMIT
    SESSIONS_PER_USER          12
    CPU_PER_SESSION            UNLIMITED
    CPU_PER_CALL               500
    LOGICAL_READS_PER_CALL     1000000
    CONNECT_TIME               UNLIMITED
    IDLE_TIME                  UNLIMITED
    FAILED_LOGIN_ATTEMPTS      5
    PASSWORD_LOCK_TIME         1/24
    PASSWORD_LIFE_TIME         UNLIMITED
    PASSWORD_REUSE_MAX         10
    PASSWORD_REUSE_TIME        365;
-- PASSWORD_LIFE_TIME UNLIMITED evita que la cuenta de servicio expire y tire la
-- API; la contraseña debe rotarse manualmente según la política de la empresa.

-- -----------------------------------------------------------------------------
-- 3. Usuario de solo lectura: sin cuota, sin objetos propios.
-- -----------------------------------------------------------------------------
CREATE USER &&api_user IDENTIFIED BY "&&api_password"
    DEFAULT TABLESPACE USERS
    TEMPORARY TABLESPACE TEMP
    QUOTA 0 ON USERS
    PROFILE &&api_profile
    ACCOUNT UNLOCK;

GRANT CREATE SESSION TO &&api_user;

-- -----------------------------------------------------------------------------
-- 4. SELECT solo sobre las vistas publicadas (una línea por vista de
--    app/routers/__init__.py -> VIEW_MODULES). En la base de prueba las vistas
--    IA_* están en SYSADMIN: usar DEFINE owner_schema = SYSADMIN.
--    Si una vista lee tablas de OTRO esquema, el dueño de la vista necesita
--    SELECT ... WITH GRANT OPTION sobre esas tablas para poder otorgar la vista.
-- -----------------------------------------------------------------------------
GRANT SELECT ON &&owner_schema..IA_CAMPOS                      TO &&api_user;
GRANT SELECT ON &&owner_schema..IA_CAMPOS_PLANTAS_DISTANCIAS   TO &&api_user;
GRANT SELECT ON &&owner_schema..IA_CAMPOS_PRODUCTORES          TO &&api_user;
GRANT SELECT ON &&owner_schema..IA_CATAC                       TO &&api_user;
GRANT SELECT ON &&owner_schema..IA_CHOFERES                    TO &&api_user;
GRANT SELECT ON &&owner_schema..IA_CHOFERES_ACTIVOS            TO &&api_user;
GRANT SELECT ON &&owner_schema..IA_CHOFERES_NO_ACTIVOS         TO &&api_user;
GRANT SELECT ON &&owner_schema..IA_COMPRAS_PENDIENTES_FACTURAS TO &&api_user;
GRANT SELECT ON &&owner_schema..IA_COMPRAS_PENDIENTES_NCND     TO &&api_user;
GRANT SELECT ON &&owner_schema..IA_EMPRESA_TRANSPORTE          TO &&api_user;
GRANT SELECT ON &&owner_schema..IA_IMPUESTOS_REGIMENES         TO &&api_user;
GRANT SELECT ON &&owner_schema..IA_PLANTAS                     TO &&api_user;
GRANT SELECT ON &&owner_schema..IA_PRODUCTORES                 TO &&api_user;
-- Vistas de ejemplo (V_PRODUCTOS, V_CLIENTES): no existen en la base; descomentar
-- solo si se crean, porque un GRANT sobre una vista inexistente corta el script.
-- GRANT SELECT ON &&owner_schema..V_PRODUCTOS TO &&api_user;
-- GRANT SELECT ON &&owner_schema..V_CLIENTES  TO &&api_user;

-- -----------------------------------------------------------------------------
-- 5. (Opcional) Sinónimos privados para que la API use los nombres sin esquema.
--    Alternativa (la que se usa hoy): dejar esto comentado y configurar
--    VIEW_SCHEMA=&&owner_schema en el .env de la API.
-- -----------------------------------------------------------------------------
-- CREATE SYNONYM &&api_user..IA_CAMPOS FOR &&owner_schema..IA_CAMPOS;
-- (repetir para cada vista del punto 4)

-- -----------------------------------------------------------------------------
-- 6. Verificación: el usuario debe tener SOLO CREATE SESSION y SELECT en las vistas.
-- -----------------------------------------------------------------------------
SELECT privilege FROM dba_sys_privs WHERE grantee = '&&api_user';
SELECT owner, table_name, privilege FROM dba_tab_privs WHERE grantee = '&&api_user';
SELECT granted_role FROM dba_role_privs WHERE grantee = '&&api_user';
SELECT resource_name, limit FROM dba_profiles WHERE profile = '&&api_profile' ORDER BY 1;

UNDEFINE api_password
