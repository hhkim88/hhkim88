package com.hhkim88.typofix.ui

import android.os.Bundle
import android.view.View
import androidx.appcompat.app.AppCompatActivity
import androidx.lifecycle.lifecycleScope
import androidx.recyclerview.widget.LinearLayoutManager
import com.hhkim88.typofix.data.AppDatabase
import com.hhkim88.typofix.data.TypoCorrectionEntity
import com.hhkim88.typofix.databinding.ActivityCorrectionsBinding
import kotlinx.coroutines.launch

class CorrectionsActivity : AppCompatActivity() {

    private lateinit var binding: ActivityCorrectionsBinding

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        binding = ActivityCorrectionsBinding.inflate(layoutInflater)
        setContentView(binding.root)

        val dao = AppDatabase.get(applicationContext).typoCorrectionDao()

        val adapter = CorrectionsAdapter(
            onToggle = { item, enabled ->
                lifecycleScope.launch { dao.setEnabled(item.typo, enabled) }
            },
            onDelete = { item ->
                lifecycleScope.launch { dao.deleteByTypo(item.typo) }
            }
        )

        binding.recyclerView.layoutManager = LinearLayoutManager(this)
        binding.recyclerView.adapter = adapter

        lifecycleScope.launch {
            dao.observeAll().collect { list: List<TypoCorrectionEntity> ->
                adapter.submitList(list)
                binding.emptyView.visibility = if (list.isEmpty()) View.VISIBLE else View.GONE
            }
        }
    }
}
