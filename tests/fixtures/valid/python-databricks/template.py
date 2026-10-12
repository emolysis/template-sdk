"""Test fixture: a PySpark entry. It needs Spark, so local tests skip it."""

SOURCE_PATH = {{ source_path }}
TARGET = {{ target_table }}


def run(spark):
    frame = spark.read.format("parquet").load(SOURCE_PATH)
    frame.write.mode("append").saveAsTable(TARGET)
