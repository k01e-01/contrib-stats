while inotifywait -e close_write src/ &>/dev/null
  echo "--- file change detected! reloading project ---"
  
  echo "--- formatting! ---"
  poetry run black .

  echo "--- python src/main.py -i local/in.toml ---"
  poetry run python src/main.py -i local/in.toml -o local/out.toml
  echo "--- exited with code $status ---"
end

